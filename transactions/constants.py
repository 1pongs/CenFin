transaction_type_TX_MAP = {
    # tx                tsrc        tdest       assetsrc   assetdest
    "income":   ("outside",  "income",   "outside",   "liquid"),
    "expense":  ("expense",  "outside",  "liquid",    "outside"),
    "premium_payment": ("expense", "outside", "liquid", "outside"),
    "transfer": ("transfer", "transfer", "liquid",    "liquid"),
    "buy_acquisition":("transfer", "buy_acquisition","liquid",    "non_liquid"),
    "sell_acquisition":("buy_acquisition","transfer","non_liquid","liquid"),
    "loan_disbursement":("outside", "loan_disbursement", "outside", "liquid"),
    "loan_repayment":("expense", "outside", "liquid", "outside"),
    "cc_purchase":("expense", "outside", "credit", "outside"),
    "cc_payment":("transfer", "transfer", "liquid", "credit"),
}

TXN_TYPE_CHOICES = (("","---------"),)+ tuple((key, key.replace('_', ' ').title())
                                            for key in transaction_type_TX_MAP)

ASSET_TYPE_CHOICES = [
    ("", "---------"),
    ("liquid", "Liquid"),
    ("non_liquid", "Non-Liquid"),
    ("outside", "Outside"),
    ("credit", "Credit"),
]