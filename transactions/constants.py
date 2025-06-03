transaction_type_TX_MAP = {
    # tx                tsrc        tdest       assetsrc   assetdest
    "Income":   ("outside",  "income",   "outside",   "liquid"),
    "Expense":  ("expense",  "outside",  "liquid",    "outside"),
    "Transfer": ("transfer", "transfer", "liquid",    "liquid"),
    "Buy Asset":("transfer", "buy_asset","liquid",    "non_liquid"),
    "Sell Asset":("buy_asset","transfer","non_liquid","liquid"),
}

TXN_TYPE_CHOICES = (("","---------"),)+ tuple((key, key.replace('_', ' ').title())
                                              for key in transaction_type_TX_MAP)
