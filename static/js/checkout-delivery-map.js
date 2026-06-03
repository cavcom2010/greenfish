(function () {
    const METERS_PER_MILE = 1609.344;
    const EARTH_MILES = 3958.7613;

    function distanceMiles(lat1, lng1, lat2, lng2) {
        const toRadians = value => value * Math.PI / 180;
        const dLat = toRadians(lat2 - lat1);
        const dLng = toRadians(lng2 - lng1);
        const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLng / 2) ** 2;
        return EARTH_MILES * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
    }

    function addressComponent(components, types) {
        const match = (components || []).find(component => types.some(type => component.types.includes(type)));
        return match ? match.long_name : "";
    }

    function emitValidity(valid) {
        document.dispatchEvent(new CustomEvent("checkout-delivery:validity", {
            detail: { valid: Boolean(valid) }
        }));
    }

    function loadGoogleMaps(config) {
        if (window.google?.maps?.places) {
            return Promise.resolve(window.google.maps);
        }
        if (window.__checkoutDeliveryMapPromise) {
            return window.__checkoutDeliveryMapPromise;
        }

        window.__checkoutDeliveryMapPromise = new Promise((resolve, reject) => {
            window.__checkoutDeliveryMapReady = () => resolve(window.google.maps);
            const script = document.createElement("script");
            const params = new URLSearchParams({
                key: config.apiKey,
                libraries: "places,marker",
                callback: "__checkoutDeliveryMapReady",
                loading: "async"
            });
            if (config.mapId) {
                params.set("map_ids", config.mapId);
            }
            script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
            script.async = true;
            script.defer = true;
            script.onerror = () => reject(new Error("Google Maps failed to load."));
            document.head.appendChild(script);
        });
        return window.__checkoutDeliveryMapPromise;
    }

    function createMarker(map, position, title, type) {
        const markerApi = window.google?.maps?.marker;
        if (markerApi?.AdvancedMarkerElement) {
            const node = document.createElement("div");
            node.className = `checkout-map-pin checkout-map-pin-${type}`;
            node.setAttribute("aria-label", title);
            node.innerHTML = `<span>${type === "shop" ? "S" : "D"}</span>`;
            return new markerApi.AdvancedMarkerElement({ map, position, title, content: node });
        }
        return new google.maps.Marker({ map, position, title });
    }

    function init(config) {
        const form = document.getElementById("checkoutForm");
        const card = document.getElementById("deliveryAddressCard");
        const search = document.getElementById("deliveryAddressSearch");
        const mapElement = document.getElementById("deliveryMap");
        const status = document.getElementById("deliveryMapStatus");
        const serviceInput = document.getElementById(config.serviceInputId || "serviceTypeInput");
        const fields = {
            line1: document.getElementById("addressLine1"),
            line2: document.getElementById("addressLine2"),
            city: document.getElementById("deliveryCity"),
            postcode: document.getElementById("deliveryPostcode"),
            formatted: document.getElementById("deliveryFormattedAddress"),
            placeId: document.getElementById("deliveryPlaceId"),
            latitude: document.getElementById("deliveryLatitude"),
            longitude: document.getElementById("deliveryLongitude")
        };
        const configured = Boolean(config.configured && config.apiKey && mapElement);
        let map;
        let customerMarker;
        let valid = !configured || Boolean(fields.latitude?.value && fields.longitude?.value);
        let initialized = false;

        function setStatus(message, state) {
            if (!status) return;
            status.textContent = message;
            status.dataset.state = state || "neutral";
        }

        function clearSelection() {
            valid = !configured;
            ["formatted", "placeId", "latitude", "longitude"].forEach(key => {
                if (fields[key]) fields[key].value = "";
            });
            setStatus(config.readyMessage || "Choose an address to check delivery availability.", "neutral");
            emitValidity(valid);
        }

        function fillAddress(place) {
            const components = place.address_components || [];
            const streetNumber = addressComponent(components, ["street_number"]);
            const route = addressComponent(components, ["route"]);
            const city = addressComponent(components, ["postal_town", "locality", "administrative_area_level_2"]);
            const postcode = addressComponent(components, ["postal_code"]);
            if (fields.line1) fields.line1.value = [streetNumber, route].filter(Boolean).join(" ") || place.name || "";
            if (fields.city && city) fields.city.value = city;
            if (fields.postcode && postcode) fields.postcode.value = postcode.toUpperCase();
            if (fields.formatted) fields.formatted.value = place.formatted_address || "";
            if (fields.placeId) fields.placeId.value = place.place_id || "";
        }

        function markPlace(place) {
            if (!place.geometry?.location) {
                clearSelection();
                setStatus("That address could not be located. Choose a result from the suggestions.", "error");
                return;
            }

            const lat = place.geometry.location.lat();
            const lng = place.geometry.location.lng();
            const distance = distanceMiles(config.shopLat, config.shopLng, lat, lng);
            valid = distance <= Number(config.radiusMiles);
            if (fields.latitude) fields.latitude.value = lat.toFixed(6);
            if (fields.longitude) fields.longitude.value = lng.toFixed(6);
            fillAddress(place);

            if (map) {
                const position = { lat, lng };
                if (!customerMarker) {
                    customerMarker = createMarker(map, position, "Delivery address", "customer");
                } else if (typeof customerMarker.setPosition === "function") {
                    customerMarker.setPosition(position);
                } else {
                    customerMarker.position = position;
                }
                const bounds = new google.maps.LatLngBounds();
                bounds.extend({ lat: config.shopLat, lng: config.shopLng });
                bounds.extend(position);
                map.fitBounds(bounds, window.innerWidth < 720 ? 48 : 84);
            }

            if (valid) {
                setStatus(`Delivery available. This address is ${distance.toFixed(1)} miles from the shop.`, "success");
            } else {
                setStatus(`Outside our ${Number(config.radiusMiles).toFixed(1)} mile delivery area. Choose pickup or another address.`, "error");
            }
            emitValidity(valid);
        }

        function initializeMap() {
            if (!configured || initialized) return;
            initialized = true;
            card?.classList.add("delivery-map-loading");
            setStatus("Loading live delivery map...", "loading");

            loadGoogleMaps(config)
                .then(() => {
                    const shopPosition = { lat: Number(config.shopLat), lng: Number(config.shopLng) };
                    map = new google.maps.Map(mapElement, {
                        center: shopPosition,
                        zoom: 13,
                        mapId: config.mapId || undefined,
                        clickableIcons: false,
                        streetViewControl: false,
                        fullscreenControl: false,
                        mapTypeControl: false,
                        zoomControl: true,
                        gestureHandling: "greedy"
                    });
                    createMarker(map, shopPosition, config.shopName || "Shop", "shop");
                    const radiusCircle = new google.maps.Circle({
                        map,
                        center: shopPosition,
                        radius: Number(config.radiusMiles) * METERS_PER_MILE,
                        fillColor: "#FF6B35",
                        fillOpacity: 0.11,
                        strokeColor: "#FF6B35",
                        strokeOpacity: 0.86,
                        strokeWeight: 2
                    });
                    map.fitBounds(radiusCircle.getBounds(), window.innerWidth < 720 ? 22 : 40);
                    if (search && google.maps.places) {
                        const autocomplete = new google.maps.places.Autocomplete(search, {
                            componentRestrictions: { country: "gb" },
                            fields: ["address_components", "formatted_address", "geometry", "name", "place_id"],
                            types: ["address"]
                        });
                        autocomplete.addListener("place_changed", () => markPlace(autocomplete.getPlace()));
                    }
                    card?.classList.remove("delivery-map-loading");
                    setStatus(config.readyMessage || "Choose an address to check delivery availability.", "neutral");
                    emitValidity(valid);
                })
                .catch(() => {
                    card?.classList.remove("delivery-map-loading");
                    setStatus("Map could not load. Enter the address manually and the shop will confirm delivery.", "error");
                    valid = true;
                    emitValidity(valid);
                });
        }

        function setServiceSelected(selected) {
            const isSelected = Boolean(selected);
            card?.classList.toggle("delivery-card-active", isSelected);
            if (isSelected) {
                card?.removeAttribute("hidden");
                if (configured) {
                    initializeMap();
                    window.setTimeout(() => {
                        if (map) google.maps.event.trigger(map, "resize");
                    }, 180);
                }
                window.setTimeout(() => search?.focus({ preventScroll: true }), 160);
            }
            emitValidity(valid || !isSelected || !configured);
        }

        ["line1", "line2", "city", "postcode"].forEach(key => {
            fields[key]?.addEventListener("input", () => {
                if (configured) clearSelection();
            });
        });

        form?.addEventListener("submit", event => {
            const isDelivery = serviceInput?.value === "delivery";
            if (configured && isDelivery && !valid) {
                event.preventDefault();
                setServiceSelected(true);
                setStatus("Choose an address from the suggestions before placing a delivery order.", "error");
                search?.focus();
            }
        });

        setServiceSelected(serviceInput?.value === "delivery");
        return {
            setServiceSelected,
            isValid: () => valid
        };
    }

    window.CheckoutDeliveryMap = { init };
})();
