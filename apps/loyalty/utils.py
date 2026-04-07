"""Utility functions for loyalty system."""
import secrets
import string


def generate_referral_code(length=8):
    """Generate a random referral code."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def format_points(points):
    """Format points for display."""
    if points >= 1000:
        return f"{points / 1000:.1f}k"
    return str(points)


def get_loyalty_tier(total_points_earned_lifetime):
    """Determine loyalty tier based on lifetime points."""
    if total_points_earned_lifetime >= 2000:
        return {
            "name": "VIP Gold",
            "color": "#FFD700",
            "emoji": "👑",
            "multiplier": 1.5,
            "benefits": ["1.5x points on all orders", "Priority delivery", "Exclusive offers"]
        }
    elif total_points_earned_lifetime >= 1000:
        return {
            "name": "Silver",
            "color": "#C0C0C0",
            "emoji": "🥈",
            "multiplier": 1.25,
            "benefits": ["1.25x points on all orders", "Early access to deals"]
        }
    elif total_points_earned_lifetime >= 500:
        return {
            "name": "Bronze",
            "color": "#CD7F32",
            "emoji": "🥉",
            "multiplier": 1.1,
            "benefits": ["1.1x points on all orders"]
        }
    return {
        "name": "Member",
        "color": "#6B7280",
        "emoji": "🍟",
        "multiplier": 1.0,
        "benefits": ["Earn points on every order"]
    }
