from decimal import Decimal

ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen"
]

TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"
]

def _two_digits_to_words(n: int) -> str:
    if n < 20:
        return ONES[n]
    tens_digit = n // 10
    ones_digit = n % 10
    if ones_digit:
        return f"{TENS[tens_digit]} {ONES[ones_digit]}"
    return TENS[tens_digit]

def _three_digits_to_words(n: int) -> str:
    hundreds = n // 100
    remainder = n % 100
    res = []
    if hundreds:
        res.append(f"{ONES[hundreds]} Hundred")
    if remainder:
        res.append(_two_digits_to_words(remainder))
    return " ".join(res)

def amount_to_indian_words(amount: Decimal | float | int) -> str:
    """
    Converts a numerical amount in Indian Rupees into official words format.
    Example: 125450.50 -> 'Rupees One Lakh Twenty-Five Thousand Four Hundred Fifty and Fifty Paise Only'
    """
    dec_amount = Decimal(str(amount))
    if dec_amount < 0:
        return "Negative " + amount_to_indian_words(abs(dec_amount))

    rupees = int(dec_amount)
    paise = int(round((dec_amount - rupees) * 100))

    if rupees == 0 and paise == 0:
        return "Zero Rupees Only"

    parts = []

    # Indian numbering: Crores (10,000,000), Lakhs (100,000), Thousands (1,000), Hundreds (100)
    crores = rupees // 10000000
    rupees %= 10000000

    lakhs = rupees // 100000
    rupees %= 100000

    thousands = rupees // 1000
    rupees %= 1000

    if crores:
        parts.append(f"{_two_digits_to_words(crores)} Crore")
    if lakhs:
        parts.append(f"{_two_digits_to_words(lakhs)} Lakh")
    if thousands:
        parts.append(f"{_two_digits_to_words(thousands)} Thousand")
    if rupees:
        parts.append(_three_digits_to_words(rupees))

    rupees_str = " ".join(parts).strip()
    if not rupees_str:
        rupees_str = "Zero"

    result = f"Rupees {rupees_str}"
    if paise:
        result += f" and {_two_digits_to_words(paise)} Paise"
    result += " Only"

    return result

def format_inr(amount: Decimal | float | int) -> str:
    """
    Formats an amount with the Indian Rupee symbol and Indian numbering format.
    Example: 154200.00 -> '₹1,54,200.00'
    """
    dec = Decimal(str(amount))
    is_negative = dec < 0
    dec = abs(dec)
    
    parts = f"{dec:.2f}".split(".")
    integer_part = parts[0]
    decimal_part = parts[1]

    if len(integer_part) <= 3:
        formatted = integer_part
    else:
        last3 = integer_part[-3:]
        remaining = integer_part[:-3]
        chunks = []
        while len(remaining) > 2:
            chunks.append(remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            chunks.append(remaining)
        chunks.reverse()
        formatted = ",".join(chunks) + "," + last3

    sign = "-" if is_negative else ""
    return f"{sign}₹{formatted}.{decimal_part}"
