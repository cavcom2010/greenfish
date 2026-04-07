"""
Accounts app - Authentication and customer profiles.

This app combines authentication (User model) with customer business logic
(CustomerProfile) for historical database compatibility.

In a clean architecture, these would be separate:
- authentication: User model only
- customers: CustomerProfile, Address models

Structure:
- models.py: User (auth), CustomerProfile (business)
- views.py: Profile management, account settings
- forms.py: Registration, profile editing
"""
