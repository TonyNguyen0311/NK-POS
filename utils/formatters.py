"""
This file contains utility functions for formatting numbers and currency.
"""
import re

def format_currency(number, currency_symbol="₫"):
    """
    Formats a number as Vietnamese currency with a dot as a thousand separator.
    
    Args:
        number (int or float): The number to format.
        currency_symbol (str): The currency symbol to append.
        
    Returns:
        str: The formatted currency string.
    """
    if number is None:
        return ""
    try:
        return f"{int(number):,}".replace(",", ".") + f" {currency_symbol}"
    except (ValueError, TypeError):
        return str(number)

def format_number(number):
    """
    Formats a number with a dot as a thousand separator.
    
    Args:
        number (int or float): The number to format.
        
    Returns:
        str: The formatted number string.
    """
    if number is None:
        return ""
    try:
        return f"{int(number):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(number)

def parse_currency(price_str: str) -> int:
    """Converts a formatted currency string (e.g., '6.500.000 đ') to an integer."""
    if not isinstance(price_str, str):
        return 0
    try:
        # Remove all non-digit characters
        cleaned_str = re.sub(r'\D', '', price_str)
        return int(cleaned_str)
    except (ValueError, TypeError):
        return 0
