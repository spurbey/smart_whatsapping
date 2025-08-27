from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional,List
from datetime import datetime

app = FastAPI(title = "Ecomomerce Automationn API", version = "1.0.0")

class WebhookMessage(BaseModel):
    message_id:str
    from_phone:str
    message_text:str
    timestamp:str
    customer_name: Optional[str] = None

class ShopifyOrder(BaseModel):
    """
    This defines what a Shopify order webhook should look like
    """
    order_id: str
    customer_email: str
    total_price: float
    order_status: str
    items: List[dict]        # List of items in the order
    created_at: str

received_messages = []
received_orders = []


@app.get("/")
def read_root():
    return {"message": "E-commerce Automation API is running!"}

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "ecommerce-automation-api",
        "timestamp": datetime.now().isoformat(),
        "endpoints": ["/webhook/whatsapp", "/webhook/shopify", "/messages", "/orders"]
    }