# Amounts extracted from receipt images in dataset/media/images/ (image_01..image_16).
# Each key is the financial-event id whose `amount` column is blank in financial_events.csv.
# Verified manually against the actual receipt images.

# (amount, currency, note)
IMAGE_EVENT_AMOUNTS = {
    # image_01: Pay slip Aug-2019, M NURHUDA SY, Net Pay IDR 4,365,000
    "event_253":  (4365000, "IDR", "Aug 2019 net salary (Net Pay on payslip)"),
    # image_02: Rent receipt #9453 dated 11/08/23; total 2,00,000; received 1,00,000;
    # event_1442 description is "Outstanding rent balance" -> the outstanding part is 100,000
    "event_1442": (100000, "INR", "Outstanding rent balance (total 200000, 100000 received)"),
    # image_03: RIDDHI SIDDHI bill 27/02/2026, Net Amount 41272.0 (cash paid)
    "event_1545": (41272, "INR", "Bulk groceries and pantry purchase (SnapBizz net amount)"),
    # image_04: delivery item details, Item Bill Rs 2854.00
    "event_1700": (2854, "INR", "Delivered grocery order (item bill)"),
    # image_05: Airtel bill, amount due till 06-Feb-2026 = Rs 704.05 (event pending 2026-02-06)
    "event_1786": (704.05, "INR", "Outstanding telecom bill (amount due till 06-Feb-2026)"),
    # image_06: Blink Commerce tax invoice, Grand Total Rs 1,995.00
    "event_3051": (1995, "INR", "Grocery tax invoice (grand total)"),
    # image_07: Nagarjuna restaurant, Grand Total Rs 8,528.00, dated 29-10-2025
    "event_3231": (8528, "INR", "Restaurant tax invoice (grand total)"),
    # image_08: property maintenance receipt 24-07-2026, total received Rs 15,339.00
    "event_4535": (15339, "INR", "Property maintenance invoice (total received)"),
    # image_09: water bill receipt 07-06-2026, Rs 723.00
    "event_5170": (723, "INR", "Water bill Jan-Mar 2026 (total received)"),
    # image_10: large grocery tax invoice, Grand Total Rs 79,679.26
    "event_6033": (79679.26, "INR", "Large grocery tax invoice (grand total / balance due)"),
    # image_11: Jeevan Hospital provisional bill, Amount Payable Rs 3,650.00
    "event_6859": (3650, "INR", "Hospital bill payable (amount payable)"),
    # image_12: CityCab receipt 01/10/2025, total $33.50
    "event_7307": (33.50, "USD", "Taxi fare (subtotal/total)"),
    # image_13: tote bags order, Total Paid Rs 2,298
    "event_7941": (2298, "INR", "Tote bag order (total paid)"),
    # image_14: handwritten pharmacy bill, total Rs 4,543.00
    "event_9421": (4543, "INR", "Pharmacy purchase (total)"),
    # image_15: Indigo flight invoice 07-Jun-2026, Grand Total Rs 9,968.00
    "event_9806": (9968, "INR", "Airline ticket purchase (grand total)"),
    # image_16: EV charging receipt 03/09/2026, total Rs 393.22 (wallet)
    "event_10521": (393.22, "INR", "EV charging wallet payment (total)"),
}


def get_event_amount(event_id):
    row = IMAGE_EVENT_AMOUNTS.get(event_id)
    return row[0] if row else None
