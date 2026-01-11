import pandas as pd

s = input("Enter the filename: ")
df = pd.read_excel(s)
print(df.head())
print(df.columns)