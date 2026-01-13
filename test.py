from scrapy import Selector

with open("test.html", "r", encoding="utf-8") as f:
    raw_html = f.read()
    
sel = Selector(text=raw_html)

script = sel.xpath('//script[contains(text(),"var params = new Map();")]/text()').get()
period_id = script.split("params.set('periodId',")[1].split(")")[0].strip()
period_type_id = script.split("params.set('periodType',")[1].split(")")[0].strip()

print("Period ID:", period_id)
print("Period Type ID:", period_type_id)