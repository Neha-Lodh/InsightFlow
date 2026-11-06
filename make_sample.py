import numpy as np, pandas as pd
r = np.random.default_rng(1); n = 1000
d = pd.DataFrame({"Order_ID": range(1, n+1), "Order Date": pd.to_datetime("2025-01-01") + pd.to_timedelta(r.integers(0, 365, n), "D"),
  "Region": r.choice(["North","South","East","West"], n), "Category": r.choice(["Electronics","Furniture","Clothing"], n),
  "Product": r.choice([f"P{i}" for i in range(1, 9)], n), "Discount": r.choice([0,.1,.2,.3], n), "Sales": r.gamma(3, 120, n).round(2)})
d["Profit"] = (d.Sales * (0.3 - d.Discount) + r.normal(0, 10, n)).round(2)
d.to_csv("sample_sales.csv", index=False)
