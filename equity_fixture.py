import pandas as pd
from equity_data import company_events, valuation_row, relative_valuation


def make_bundle(ticker="FPT", period="3mo"):
    company={"ticker":ticker,"source_url":f"https://simplize.vn/co-phieu/{ticker}","fetched":"2026-09-17T12:00:00+07:00",
             "summary":{"ticker":ticker,"name":ticker,"industryActivity":"CNTT","bcIndustryGroupId":48,
                        "peRatio":15.,"pbRatio":3.,"marketCap":100e9,"epsRatio":5000.,"bookValue":25000.,"analysisUpdated":"17/09/2026"},
             "events":[{"title":"Cổ tức","exDividendDate":"28/05/2026","recordDate":"29/05/2026","executionDate":"10/06/2026"}]}
    rows=[valuation_row(company)]
    for name, pe in [("CMG",12),("ELC",18)]:
        rows.append({**rows[0],"Mã":name,"P/E (TTM)":pe})
    return {"ticker":ticker,"period":period,"company":company,"errors":[],"events":company_events(company),
            "ownership":[{"Cổ đông":"Cá nhân","Tỷ lệ (%)":60}],"peers":rows,"relative":relative_valuation(rows),
            "prices":pd.DataFrame({"date":pd.to_datetime(["2026-09-15","2026-09-16"]),"close":[70000,71000],"volume":[200,300]}),
            "price_meta":{"source":"Test","fetched":"17/09/2026","adjustment":"Chưa xác định"}}
