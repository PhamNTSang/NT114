import random

from locust import HttpUser, between, task
class OnlineBoutiqueUser(HttpUser):
    wait_time = between(1, 5)

    # Product IDs from Online Boutique
    PRODUCT_IDS = [
        "OLJCESPC7Z",
        "66VCHSJNUP",
        "1YMWWN1N4O",
        "L9ECAV7KIM",
        "2ZYFJ3GM2N",
        "0PUK6V6EV0",
        "LS4PSXUNUM",
        "9SIQT8TOJO",
        "6E92ZMYYFZ",
    ]

    CURRENCIES = ["USD", "EUR", "JPY", "GBP", "CAD"]

    @task(10)
    def browse_homepage(self):
        self.client.get("/")

    @task(5)
    def browse_product(self):
        product_id = random.choice(self.PRODUCT_IDS)
        self.client.get(f"/product/{product_id}")

    @task(3)
    def add_to_cart(self):
        product_id = random.choice(self.PRODUCT_IDS)
        self.client.post(
            "/cart",
            data={
                "product_id": product_id,
                "quantity": random.randint(1, 5),
            },
        )

    @task(2)
    def view_cart(self):
        self.client.get("/cart")

    @task(1)
    def checkout(self):
        self.client.post(
            "/cart/checkout",
            data={
                "email": "test@example.com",
                "street_address": "123 Test St",
                "zip_code": "10001",
                "city": "New York",
                "state": "NY",
                "country": "US",
                "credit_card_number": "4111111111111111",
                "credit_card_expiration_month": "12",
                "credit_card_expiration_year": "2030",
                "credit_card_cvv": "123",
            },
        )

    @task(2)
    def change_currency(self):
        currency = random.choice(self.CURRENCIES)
        self.client.post("/setCurrency", data={"currency_code": currency})
