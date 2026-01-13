import httpx
from scrapy import Selector
from fastapi import FastAPI, Request
from datetime import datetime, timedelta
import logging
import html
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()

LOGIN_URL = "https://my.frequense.com/Account/Login?ReturnUrl=%2F"


def get_yesterday(days=1):
    return (datetime.now() - timedelta(days=days)).date()


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


def extract_leads(raw_html: str):
    yesterday = get_yesterday()
    sel = Selector(text=raw_html)

    rows = sel.css("#table-body tr")
    if not rows:
        return []

    leads = []
    for row in rows:
        entry_str = row.css('td[data-colname="EntryDate"]::text').get('')
        entry_date = datetime.strptime(entry_str, "%d %b %Y").date()

        if entry_date == yesterday:
            leads.append({
                "Name": row.css('td[data-colname="FullName"]::text').get(''),
                "Email": row.css('td[data-colname="EmailAddress"]::text').get(''),
                "Phone": row.css('td[data-colname="PhoneNumbers.CellPhone"]::text').get('')
            })

    return leads


async def get_leads(session: httpx.AsyncClient):
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

    return {"status": True, "leads": extract_leads(res.text)}


@app.post("/leads")
async def fetch_leads(request: Request):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    async with httpx.AsyncClient(follow_redirects=True, timeout=200) as session:
        try:
            logged = await login(username, password, session)
            if not logged["status"]:
                return {"error": logged["error"]}

            result = await get_leads(session)
            if not result["status"]:
                return {"error": result["error"]}

            return {
                "total": len(result["leads"]),
                "leads": result["leads"]
            }

        except Exception as e:
            logging.exception("Error while fetching leads")
            return {"error": str(e)}



def extract_prospects(raw_html: str):
    sel = Selector(text=raw_html)
    yesterday = get_yesterday()
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
        if entry_date == yesterday:
            prospects.append({
                "FirstName": row.css('td[data-colname="FirstName"]::text').get(''),
                "LastName": row.css('td[data-colname="LastName"]::text').get(''),
                "Email": row.css('td[data-colname="Email"]::text').get(''),
                "Phone": row.css('td[data-colname="Cell"]::text').get('')
            })

    return prospects


async def get_prospects(session: httpx.AsyncClient):
    res = await session.get("https://my.frequense.com/Reports/CompanyReports")
    token = Selector(text=res.text).xpath('//*[@name="__RequestVerificationToken"]/@value').get('')
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
        "&reportId=20009&customerId=36255&periodType=2&periodId=22"
    )

    res = await session.post(url, headers=headers, data=payload)

    if res.status_code != 200:
        return {"status": False, "error": f"Fetch failed {res.status_code}"}

    return {"status": True, "prospects": extract_prospects(res.text)}

@app.post("/prospects")
async def fetch_prospects(request: Request):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")

    async with httpx.AsyncClient(follow_redirects=True, timeout=200) as session:
        try:
            logged = await login(username, password, session)
            if not logged["status"]:
                return {"error": logged["error"]}

            result = await get_prospects(session)
            if not result["status"]:
                return {"error": result["error"]}

            return {
                "total": len(result["prospects"]),
                "prospects": result["prospects"]
            }

        except Exception as e:
            logging.exception("Error while fetching prospects")
            return {"error": str(e)}


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

async def extract_customers(raw_html: str, session: httpx.AsyncClient, token: str):
    sel = Selector(text=raw_html)
    yesterday = get_yesterday()
    rows = sel.css("#table-body tr")
    customers = []
    for row in rows:
        entry_str = row.css('td[data-colname="OrderDateOrderDate__shortdate"] time::text').get('')
        try:
            entry_date = datetime.strptime(entry_str, "%m/%d/%Y %I:%M:%S %p").date()
        except ValueError:
            entry_date = datetime.strptime(entry_str, "%Y-%m-%dT%H:%M:%S%z").date()
        if entry_date == yesterday:
            customer = {}
            customer['CustomerName'] = row.css('td[data-colname="CustomerName"]::text').get('')
            customer_id = row.css('td[data-colname="CustomerId"]::text').get('')
            customer['Email'], phone = await fetch_customer_summary(customer_id, session) or ('', '')
            order_details = await fetch_customer_order_details(customer_id, session, token) or ('', [])
            customer['Phone'] = order_details[0] if order_details[0] else phone
            customer['Orders'] = order_details[1]
            customers.append(customer)

    return customers

async def get_customers(session: httpx.AsyncClient):
    res = await session.get("https://my.frequense.com/Reports/CompanyReports")
    sel = Selector(text=res.text)
    token = sel.xpath('//*[@name="__RequestVerificationToken"]/@value').get('')
    customer_id = sel.xpath("//*[contains(text(),'ID#')]/text()").re_first(r'ID#\s*(\d+)')
    url = "https://my.frequense.com/Reports/CompanyReports?handler=Query"
    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "requestverificationtoken": token,
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0"
    }
    payload = f"teqReportId=08e60ec5e30449aa84a45ad8f1af75c6&filter%5BOffset%5D=0&filter%5BLimit%5D=50&filter%5BOrderByColumn%5D=OrderDateOrderDate__shortdate&filter%5BOrderByMethod%5D=DESC&filter%5BSearchList%5D%5B0%5D%5BSearchFilter%5D=Level&filter%5BSearchList%5D%5B0%5D%5BSearchMethod%5D=eq&filter%5BSearchList%5D%5B0%5D%5BSearchValue%5D=1&reportId=20007&customerId={customer_id}&periodType=1&periodId=92"
    res = await session.post(url, headers=headers, data=payload)
    if res.status_code != 200:
        return {"status": False, "error": f"Fetch failed {res.status_code}"}
    return {"status": True, "customers": await extract_customers(res.text, session, token)}

@app.post("/customers")
async def fetch_customers(request: Request):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")

    async with httpx.AsyncClient(follow_redirects=True, timeout=200) as session:
        try:
            logged = await login(username, password, session)
            if not logged["status"]:
                return {"error": logged["error"]}

            result = await get_customers(session)
            if not result["status"]:
                return {"error": result["error"]}

            return {
                "total": len(result["customers"]),
                "customers": result["customers"]
            }

        except Exception as e:
            logging.exception("Error while fetching customers")
            return {"error": str(e)}
        
@app.get("/")
def root():
    return {"message": "Frequense API is running"}