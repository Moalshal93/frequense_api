import httpx
from scrapy import Selector
from fastapi import FastAPI, Request
from datetime import datetime, timedelta
import logging
import html
import json
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()

LOGIN_URL = "https://my.frequense.com/Account/Login?ReturnUrl=%2F"


def get_yesterday(days=1):
    return (datetime.now() - timedelta(days=days)).date()

def get_date_days_ago(days=7):
    days_list = []
    for day in range(1, days + 1):
        days_list.append((datetime.now() - timedelta(days=day)).date())
    return days_list

async def login(username: str, password: str, session: httpx.AsyncClient):
    r = await session.get(LOGIN_URL)
    if r.status_code != 200:
        return {"status": False, "error": f"Failed to load login page"}

    sel = Selector(text=r.text)
    token = sel.xpath('//*[@name="__RequestVerificationToken"]/@value').get()

    if not token:
        return {"status": False, "error": "Missing verification token"}

    payload = {
        "Login.Username": username,
        "Login.Password": password,
        "Login.RememberMe": "true",
        "__RequestVerificationToken": token
    }

    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": "Mozilla/5.0"
    }

    r = await session.post(LOGIN_URL, data=payload, headers=headers)

    if "Invalid login" in r.text:
        return {"status": False, "error": "Invalid credentials"}

    return {"status": True, "token": token}


def extract_leads(raw_html: str, days=None):
    
    if not days:
        days = [get_yesterday()]
    else:
        days = get_date_days_ago(days)
        
    sel = Selector(text=raw_html)

    rows = sel.css("#table-body tr")
    if not rows:
        return []

    leads = []
    for row in rows:
        entry_str = row.css('td[data-colname="EntryDate"]::text').get('')
        entry_date = datetime.strptime(entry_str, "%d %b %Y").date()

        if entry_date in days:
            leads.append({
                "Name": row.css('td[data-colname="FullName"]::text').get(''),
                "Email": row.css('td[data-colname="PublicProfile.Email"]::text').get(''),
                "Phone": row.css('td[data-colname="PublicProfile.Phone"]::text').get('').replace("+", "")
            })

    return leads


async def get_leads(session: httpx.AsyncClient, days=1):
    res = await session.get("https://my.frequense.com/Organization/TeamLeads")
    token = Selector(text=res.text).xpath('//*[@name="__RequestVerificationToken"]/@value').get('')

    url = "https://my.frequense.com/Organization/TeamLeads?handler=Query"

    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "requestverificationtoken": token,
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0"
    }

    payload = (
        "teqReportId=f80e81bfe56a4c4bb11dfa303c9a76e3"
        "&filter%5BOffset%5D=0&filter%5BLimit%5D=500"
        "&filter%5BSearchList%5D%5B0%5D%5BSearchFilter%5D=NestedLevel"
        "&filter%5BSearchList%5D%5B0%5D%5BSearchMethod%5D=eq"
        "&filter%5BSearchList%5D%5B0%5D%5BSearchValue%5D=1"
        "&filter%5BOrderByMethod%5D=DESC"
    )

    res = await session.post(url, headers=headers, data=payload)

    if res.status_code != 200:
        return {"status": False, "error": f"Fetch failed {res.status_code}"}

    return {"status": True, "leads": extract_leads(res.text, days=days)}


@app.post("/leads")
async def fetch_leads(request: Request):
    print(request)
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    days = body.get("days", 1)
    async with httpx.AsyncClient(follow_redirects=True, timeout=200) as session:
        try:
            logged = await login(username, password, session)
            if not logged["status"]:
                return {"error": logged["error"]}

            result = await get_leads(session, days=days)
            if not result["status"]:
                return {"error": result["error"]}

            return {
                "total": len(result["leads"]),
                "leads": result["leads"]
            }

        except Exception as e:
            logging.exception("Error while fetching leads")
            return {"error": str(e)}

# curl -X POST http://127.0.0.1:8000/leads -H "Content-Type: application/json" -d "{\"username\":\"Holisticmindfulmom@gmail.com\",\"password\":\"Loveemandmol0697\",\"days\":3}"

def extract_prospects(raw_html: str, days=None):
    sel = Selector(text=raw_html)
    if not days:
        days = [get_yesterday()]
    else:
        days = get_date_days_ago(days)
    rows = sel.css("#table-body tr")
    if not rows:
        return []

    prospects = []
    for row in rows:
        entry_str = row.css('td[data-colname="EntryDate"] time::text').get('')
        try:
            entry_date = datetime.strptime(entry_str, "%m/%d/%Y %I:%M:%S %p").date()
        except ValueError:
            entry_date = datetime.strptime(entry_str, "%Y-%m-%dT%H:%M:%S%z").date()
        if entry_date in days:
            prospects.append({
                "FirstName": row.css('td[data-colname="FirstName"]::text').get(''),
                "LastName": row.css('td[data-colname="LastName"]::text').get(''),
                "Email": row.css('td[data-colname="Email"]::text').get(''),
                "Phone": row.css('td[data-colname="Cell"]::text').get('').replace("+", "")
            })

    return prospects


async def get_prospects(session: httpx.AsyncClient, days=1):
    res = await session.get("https://my.frequense.com/Reports/CompanyReports")
    sel = Selector(text=res.text)
    token = sel.xpath('//*[@name="__RequestVerificationToken"]/@value').get('')
    url = "https://my.frequense.com/Reports/CompanyReports?handler=Query"


    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "requestverificationtoken": token,
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0"
    }

    payload = (
        "teqReportId=5f7ccdfcd58847bc98239bf2833515e2"
        "&filter%5BOffset%5D=0&filter%5BLimit%5D=500"
        "&filter%5BOrderByColumn%5D=EntryDate"
        "&filter%5BOrderByMethod%5D=DESC"
        f"&reportId=20009&customerId=36255"
    )

    res = await session.post(url, headers=headers, data=payload)

    if res.status_code != 200:
        return {"status": False, "error": f"Fetch failed {res.status_code}"}

    return {"status": True, "prospects": extract_prospects(res.text, days=days)}

@app.post("/prospects")
async def fetch_prospects(request: Request):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    days = body.get("days", 1)

    async with httpx.AsyncClient(follow_redirects=True, timeout=200) as session:
        try:
            logged = await login(username, password, session)
            if not logged["status"]:
                return {"error": logged["error"]}

            result = await get_prospects(session, days=days)
            if not result["status"]:
                return {"error": result["error"]}

            return {
                "total": len(result["prospects"]),
                "prospects": result["prospects"]
            }

        except Exception as e:
            logging.exception("Error while fetching prospects")
            return {"error": str(e)}


# curl -X POST http://127.0.0.1:8000/prospects -H "Content-Type: application/json" -d "{\"username\":\"Holisticmindfulmom@gmail.com\",\"password\":\"Loveemandmol0697\",\"days\":3}"

async def fetch_customer_order_details(customer_id: str, session: httpx.AsyncClient, token):
    url = "https://my.frequense.com/CustomerOverview/OrderHistoryOrders"
    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "requestverificationtoken": token,
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0"
    }
    payload = f"filter=&customerId={customer_id}"
    res = await session.post(url, headers=headers, data=payload)
    if res.status_code != 200:
        logging.error(f"Failed to fetch order details for customer {customer_id}")
        return None
    sel = Selector(text=res.text)
    raw_phone = sel.xpath('//*[@data-bs-content]/@data-bs-content').get('')
    text = html.unescape(raw_phone)
    match = re.search(r'Phone:\s*([+\d]+)', text)
    phone = match.group(1) if match else ""
    orders_xpath = sel.xpath('//*[contains(@class,"accordion-body")]//*[@class="d-flex flex-wrap d-lg-none border rounded p-2 mb-3"]')
    orders = []
    for order_xpath in orders_xpath:
        order = {}
        order['qty'] = order_xpath.xpath('.//*[contains(text(),"Qty:")]/parent::*/text()').get('').strip()
        order['description'] = order_xpath.xpath('.//*[contains(text(),"Description:")]/parent::*/text()').get('').strip()
        order['subtotal'] = order_xpath.xpath('.//*[contains(text(),"Subtotal:")]/parent::*/text()').get('').strip()
        orders.append(order)
    return phone, orders

async def fetch_customer_summary(customer_id: str, session: httpx.AsyncClient):
    url = f"https://my.frequense.com/CustomerOverview/Summary/?handler=content&customerID={customer_id}"
    res = await session.get(url)
    if res.status_code != 200:
        return None
    sel = Selector(text=res.text)
    email = "".join([i.strip() for i in sel.xpath("//a[contains(@href,'mailto')]//text()").getall() if i.strip()])
    phone = "".join([i.strip() for i in sel.xpath("//a[contains(@href,'tel:')]//text()").getall() if i.strip()])
    return email, phone

async def extract_customers(raw_html: str, session: httpx.AsyncClient, token: str, days=None):
    sel = Selector(text=raw_html)
    
    if not days:
        days = [get_yesterday()]
    else:
        days = get_date_days_ago(days)
    
    rows = sel.css("#table-body tr")
    customers = []
    for row in rows:
        entry_str = row.css('td[data-colname="OrderDateOrderDate__shortdate"] time::text').get('')
        try:
            entry_date = datetime.strptime(entry_str, "%m/%d/%Y %I:%M:%S %p").date()
        except ValueError:
            entry_date = datetime.strptime(entry_str, "%Y-%m-%dT%H:%M:%S%z").date()
        if entry_date in days:
            customer = {}
            customer['CustomerName'] = row.css('td[data-colname="CustomerName"]::text').get('')
            customer_id = row.css('td[data-colname="CustomerId"]::text').get('')
            customer['Email'], phone_1 = await fetch_customer_summary(customer_id, session) or ('', '')
            phone_2, order_details = await fetch_customer_order_details(customer_id, session, token) or ('', [])
            customer['Phone'] = phone_2.replace("+", "") if phone_2 else phone_1.replace("+", "")
            customer['Orders'] = order_details
            customers.append(customer)

    return customers

async def get_customers(session: httpx.AsyncClient, days=1):
    res = await session.get("https://my.frequense.com/Reports/CompanyReports")
    sel = Selector(text=res.text)
    token = sel.xpath('//*[@name="__RequestVerificationToken"]/@value').get('')
    customer_id = sel.xpath("//*[contains(text(),'ID#')]/text()").re_first(r'ID#\s*(\d+)')
    periods_script = sel.xpath('//script[contains(text(),"var periods")]/text()').get()
    periods_script_splitted = periods_script.split("var periods = ")[1].split(";")[0]
    periods = json.loads(periods_script_splitted)
    period_id = periods[0].get("periodId") if periods else "100"
    period_type_id = periods[0].get("periodTypeId") if periods else "1"
    
    url = "https://my.frequense.com/Reports/CompanyReports?handler=Query"
    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "requestverificationtoken": token,
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0"
    }
    payload = f"teqReportId=08e60ec5e30449aa84a45ad8f1af75c6&filter%5BOffset%5D=0&filter%5BLimit%5D=50&filter%5BOrderByColumn%5D=OrderDateOrderDate__shortdate&filter%5BOrderByMethod%5D=DESC&filter%5BSearchList%5D%5B0%5D%5BSearchFilter%5D=Level&filter%5BSearchList%5D%5B0%5D%5BSearchMethod%5D=eq&filter%5BSearchList%5D%5B0%5D%5BSearchValue%5D=1&reportId=20007&customerId={customer_id}&periodType={period_type_id}&periodId={period_id}"
    res = await session.post(url, headers=headers, data=payload)
    if res.status_code != 200:
        return {"status": False, "error": f"Fetch failed {res.status_code}"}
    return {"status": True, "customers": await extract_customers(res.text, session, token, days=days)}

@app.post("/customers")
async def fetch_customers(request: Request):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    days = body.get("days", 1)
    async with httpx.AsyncClient(follow_redirects=True, timeout=200) as session:
        try:
            logged = await login(username, password, session)
            if not logged["status"]:
                return {"error": logged["error"]}

            result = await get_customers(session, days=days)
            if not result["status"]:
                return {"error": result["error"]}

            return {
                "total": len(result["customers"]),
                "customers": result["customers"]
            }

        except Exception as e:
            logging.exception("Error while fetching customers")
            return {"error": str(e)}

# curl -X POST http://127.0.0.1:8000/customers -H "Content-Type: application/json" -d "{\"username\":\"Holisticmindfulmom@gmail.com\",\"password\":\"Loveemandmol0697\",\"days\":3}"
        
@app.get("/")
def root():
    return {"message": "Frequense API is running"}
