transaction_type_TX_MAP = {
    # tx                tsrc        tdest       assetsrc   assetdest
    "income":   ("outside",  "income",   "outside",   "liquid"),
    "expense":  ("expense",  "outside",  "liquid",    "outside"),
    "transfer": ("transfer", "transfer", "liquid",    "liquid"),
    "buy_product":("transfer", "buy_product","liquid",    "non_liquid"),
    "sell_product":("buy_product","transfer","non_liquid","liquid"),
    "buy_property": ("expense", "outside", "liquid", "outside"),
    "sell_property": ("expense", "outside", "liquid", "outside"),
}

TXN_TYPE_CHOICES = (("","---------"),)+ tuple((key, key.replace('_', ' ').title())
                                            for key in transaction_type_TX_MAP)

ASSET_TYPE_CHOICES = [
    ("", "---------"),
    ("liquid", "Liquid"),
    ("non_liquid", "Non-Liquid"),
    ("outside", "Outside"),
]