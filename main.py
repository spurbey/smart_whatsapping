"""
Complete E-commerce Automation API with Real WhatsApp Integration and Dashboard
"""

from fastapi import FastAPI, HTTPException, Depends, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import json
import logging
import os

# Import our database models and functions
from database import (
    get_database_session, create_tables,
    Customer, Order, Message, WebhookEvent,
    find_or_create_customer
)

# Import WhatsApp integration
from whatsapp_integration import WhatsAppService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize WhatsApp service (will be initialized in lifespan)
whatsapp_service = None

# Create database tables on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    global whatsapp_service
    
    # Initialize database
    create_tables()
    print("✅ Database initialized!")
    
    # Initialize WhatsApp service
    try:
        whatsapp_service = WhatsAppService()
        print("✅ WhatsApp service initialized!")
    except Exception as e:
        print(f"⚠️  WhatsApp service failed to initialize: {e}")
        print("   (App will continue without WhatsApp features)")
        whatsapp_service = None
    
    print("🚀 API started and all services initialized!")
    yield
    # --- Shutdown (optional) ---
    print("👋 API shutting down...")

app = FastAPI(
    title="E-commerce Automation API",
    version="1.0.0",
    lifespan=lifespan
)

# Dependency to get database session for each request
def get_db():
    """
    This function provides a database session to each API endpoint
    It ensures the session is properly closed after use
    """
    db = get_database_session()
    try:
        yield db
    finally:
        db.close()

# Pydantic models for API validation
class WebhookMessage(BaseModel):
    message_id: str
    from_phone: str
    message_text: str
    timestamp: str
    customer_name: Optional[str] = None

class ShopifyOrder(BaseModel):
    order_id: str
    customer_email: str
    total_price: float
    order_status: str
    items: List[dict]
    created_at: str

class SendMessageRequest(BaseModel):
    phone: str
    message: str

class InteractiveMessageRequest(BaseModel):
    phone: str
    message: str
    buttons: List[Dict[str, str]]

class MenuMessageRequest(BaseModel):
    phone: str
    title: str
    menu_items: List[Dict[str, str]]

class BroadcastRequest(BaseModel):
    message: str
    customer_segments: Optional[List[str]] = None  # "all", "vip", "new"
# Basic endpoints
@app.get("/")
def root():
    return {
        "message": "E-commerce Automation API with WhatsApp Integration",
        "version": "1.0.0",
        "features": ["WhatsApp Integration", "Shopify Webhooks", "Web Dashboard"],
        "endpoints": {
            "dashboard": "/dashboard",
            "health": "/health",
            "docs": "/docs"
        }
    }

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Comprehensive health check for all services
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }
    
    # Check database
    try:
        customer_count = db.query(Customer).count()
        order_count = db.query(Order).count()
        message_count = db.query(Message).count()
        
        health_status["services"]["database"] = {
            "status": "healthy",
            "stats": {
                "customers": customer_count,
                "orders": order_count,
                "messages": message_count
            }
        }
    except Exception as e:
        health_status["services"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    # Check WhatsApp service
    if whatsapp_service:
        health_status["services"]["whatsapp"] = {
            "status": "healthy",
            "provider": "twilio"
        }
    else:
        health_status["services"]["whatsapp"] = {
            "status": "unavailable",
            "note": "WhatsApp service not configured"
        }
    
    return health_status

# WhatsApp webhook endpoints
@app.post("/webhook/whatsapp/twilio", response_class=PlainTextResponse)
async def twilio_whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Real WhatsApp webhook from Twilio
    
    This endpoint receives actual WhatsApp messages from customers
    and immediately responds with automated replies
    """
    if not whatsapp_service:
        logger.error("WhatsApp service not available")
        return ""
    
    try:
        # Get form data from Twilio webhook
        form_data = await request.form()
        webhook_data = dict(form_data)
        
        logger.info(f"📱 Received Twilio webhook: {webhook_data}")
        
        # Process incoming message using WhatsApp service
        processed_message = whatsapp_service.process_incoming_webhook(webhook_data)
        
        # Find or create customer
        customer = find_or_create_customer(
            db=db, 
            whatsapp_phone=processed_message['from_phone']
        )
        
        # Extract customer name from WhatsApp profile if available
        profile_name = webhook_data.get('ProfileName', '')
        if profile_name and not customer.first_name:
            name_parts = profile_name.split(' ', 1)
            customer.first_name = name_parts[0]
            if len(name_parts) > 1:
                customer.last_name = name_parts[1]
            customer.updated_at = datetime.utcnow()
        
        # Save incoming message to database
        incoming_msg = Message(
            customer_id=customer.id,
            channel="whatsapp",
            direction="inbound",
            content=processed_message['message_text'],
            platform_message_id=processed_message['message_id'],
            received_at=datetime.fromisoformat(processed_message['timestamp'].replace('Z', '+00:00')),
            metadata_json=json.dumps({
                "from_phone": processed_message['from_phone'],
                "profile_name": profile_name,
                "raw_webhook": webhook_data
            })
        )
        db.add(incoming_msg)
        
        # Generate automated response
        response_text = generate_response(processed_message['message_text'], customer, db)
        
        # Save response message to database
        response_msg = Message(
            customer_id=customer.id,
            channel="whatsapp",
            direction="outbound",
            content=response_text,
            sent_at=datetime.utcnow(),
            bot_handled=True,
            metadata_json=json.dumps({
                "triggered_by_message": incoming_msg.id,
                "response_type": "automated"
            })
        )
        db.add(response_msg)
        
        # Commit all changes to database
        db.commit()
        
        logger.info(f"✅ Processed WhatsApp message from {customer.first_name or processed_message['from_phone']}")
        
        # Return TwiML response to immediately reply to customer
        twiml_response = whatsapp_service.generate_webhook_response(response_text)
        return twiml_response
        
    except Exception as e:
        logger.error(f"❌ WhatsApp webhook error: {e}")
        # Return empty response on error (Twilio won't retry)
        return ""

@app.post("/webhook/whatsapp")
def whatsapp_webhook_json(message: WebhookMessage, db: Session = Depends(get_db)):
    """
    JSON WhatsApp webhook endpoint (for testing)
    
    This is the original endpoint for testing with JSON data
    """
    logger.info(f"📱 Received JSON WhatsApp webhook from {message.from_phone}")
    
    try:
        # Find/create customer
        customer = find_or_create_customer(db=db, whatsapp_phone=message.from_phone)
        
        # Update customer name if provided
        if message.customer_name and not customer.first_name:
            name_parts = message.customer_name.split(' ', 1)
            customer.first_name = name_parts[0]
            if len(name_parts) > 1:
                customer.last_name = name_parts[1]
            customer.updated_at = datetime.utcnow()
        
        # Save incoming message
        incoming_msg = Message(
            customer_id=customer.id,
            channel="whatsapp",
            direction="inbound",
            content=message.message_text,
            platform_message_id=message.message_id,
            received_at=datetime.fromisoformat(message.timestamp.replace('Z', '+00:00'))
        )
        db.add(incoming_msg)
        
        # Generate response
        response_text = generate_response(message.message_text, customer, db)
        
        # Save response message
        response_msg = Message(
            customer_id=customer.id,
            channel="whatsapp",
            direction="outbound",
            content=response_text,
            sent_at=datetime.utcnow(),
            bot_handled=True
        )
        db.add(response_msg)
        
        # Commit all changes
        db.commit()
        
        return {
            "status": "success",
            "customer_id": customer.id,
            "message_id": incoming_msg.id,
            "response": response_text
        }
        
    except Exception as e:
        logger.error(f"❌ JSON WhatsApp webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Shopify webhook endpoint
@app.post("/webhook/shopify")
def shopify_webhook(order: ShopifyOrder, db: Session = Depends(get_db)):
    """
    Shopify order webhook - processes new orders
    """
    logger.info(f"🛒 Received Shopify webhook for order {order.order_id}")
    
    try:
        # Log raw webhook for debugging
        webhook_event = WebhookEvent(
            source="shopify",
            event_type="order.created",
            raw_data=order.json()
        )
        db.add(webhook_event)
        
        # Find or create customer
        customer = find_or_create_customer(db=db, email=order.customer_email)
        
        # Create order record
        new_order = Order(
            customer_id=customer.id,
            platform_order_id=order.order_id,
            platform="shopify",
            total_price=order.total_price,
            status=order.order_status,
            items_json=json.dumps(order.items),
            order_date=datetime.fromisoformat(order.created_at.replace('Z', '+00:00'))
        )
        db.add(new_order)
        
        # Update customer totals
        customer.total_orders += order.total_price
        customer.order_count += 1
        customer.updated_at = datetime.utcnow()
        
        # Mark webhook as processed
        webhook_event.processed = True
        webhook_event.processed_at = datetime.utcnow()
        
        # Commit all changes
        db.commit()
        
        # Trigger simple automations
        automation_actions = trigger_simple_automations(customer, new_order)
        
        # Send order confirmation via WhatsApp if customer has WhatsApp
        if customer.whatsapp_phone and whatsapp_service:
            confirmation_message = f"🎉 Order confirmed! Your order {order.order_id} for ${order.total_price} is being processed. We'll update you on the status!"
            try:
                whatsapp_result = whatsapp_service.send_message(customer.whatsapp_phone, confirmation_message)
                if whatsapp_result['status'] == 'sent':
                    # Save the confirmation message to database
                    confirmation_msg = Message(
                        customer_id=customer.id,
                        channel="whatsapp",
                        direction="outbound",
                        content=confirmation_message,
                        platform_message_id=whatsapp_result['message_id'],
                        sent_at=datetime.utcnow(),
                        bot_handled=True,
                        metadata_json=json.dumps({
                            "trigger": "order_confirmation",
                            "order_id": new_order.id
                        })
                    )
                    db.add(confirmation_msg)
                    db.commit()
                    automation_actions.append("whatsapp_confirmation_sent")
            except Exception as e:
                logger.error(f"Failed to send WhatsApp order confirmation: {e}")
        
        return {
            "status": "success",
            "customer_id": customer.id,
            "order_id": new_order.id,
            "actions_triggered": automation_actions
        }
        
    except Exception as e:
        logger.error(f"❌ Shopify webhook error: {e}")
        # Mark webhook as failed
        if 'webhook_event' in locals():
            webhook_event.processing_error = str(e)
            webhook_event.processed_at = datetime.utcnow()
            db.commit()
        raise HTTPException(status_code=500, detail=str(e))

# WhatsApp messaging endpoints
@app.post("/send-whatsapp")
def send_whatsapp_message(request: SendMessageRequest, db: Session = Depends(get_db)):
    """
    Manually send WhatsApp message (for testing and manual outreach)
    """
    if not whatsapp_service:
        raise HTTPException(status_code=503, detail="WhatsApp service not available")
    
    try:
        logger.info(f"📤 Sending WhatsApp message to {request.phone}")
        
        # Send message via WhatsApp service
        result = whatsapp_service.send_message(request.phone, request.message)
        
        if result['status'] == 'sent':
            # Find or create customer and save message to database
            customer = find_or_create_customer(db=db, whatsapp_phone=request.phone)
            
            outbound_msg = Message(
                customer_id=customer.id,
                channel="whatsapp",
                direction="outbound",
                content=request.message,
                platform_message_id=result['message_id'],
                sent_at=datetime.utcnow(),
                bot_handled=False,  # Manual send
                metadata_json=json.dumps({
                    "send_type": "manual",
                    "api_endpoint": "/send-whatsapp"
                })
            )
            db.add(outbound_msg)
            db.commit()
            
            logger.info(f"✅ WhatsApp message sent successfully to {request.phone}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Failed to send WhatsApp message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Dashboard endpoints
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """
    Serve the web dashboard
    """
    try:
        # Read the HTML file
        with open("templates/dashboard.html", "r", encoding="utf-8") as file:
            html_content = file.read()
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        return HTMLResponse(
            content="""
            <h1>Dashboard not found</h1>
            <p>Please create <code>templates/dashboard.html</code></p>
            <p>Check the documentation for the dashboard HTML code.</p>
            """, 
            status_code=404
        )

@app.get("/api/dashboard-stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Get comprehensive dashboard statistics
    """
    try:
        from sqlalchemy import func
        
        # Count totals
        customer_count = db.query(Customer).count()
        order_count = db.query(Order).count()
        message_count = db.query(Message).count()
        
        # Calculate revenue
        total_revenue = db.query(func.sum(Customer.total_orders)).scalar() or 0
        
        # Get recent activity (last 24 hours)
        since_yesterday = datetime.utcnow() - timedelta(hours=24)
        
        new_customers_24h = db.query(Customer).filter(
            Customer.created_at >= since_yesterday
        ).count()
        
        new_orders_24h = db.query(Order).filter(
            Order.created_at >= since_yesterday
        ).count()
        
        new_messages_24h = db.query(Message).filter(
            Message.created_at >= since_yesterday
        ).count()
        
        # Get top customers by revenue
        top_customers = db.query(Customer).filter(
            Customer.total_orders > 0
        ).order_by(Customer.total_orders.desc()).limit(5).all()
        
        return {
            "totals": {
                "customers": customer_count,
                "orders": order_count,
                "messages": message_count,
                "revenue": float(total_revenue)
            },
            "recent_24h": {
                "new_customers": new_customers_24h,
                "new_orders": new_orders_24h,
                "new_messages": new_messages_24h
            },
            "top_customers": [
                {
                    "name": f"{c.first_name or ''} {c.last_name or ''}".strip() or "Unknown",
                    "email": c.email,
                    "total_spent": float(c.total_orders),
                    "order_count": c.order_count
                }
                for c in top_customers
            ],
            "services": {
                "whatsapp_available": whatsapp_service is not None,
                "database_connected": True
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Dashboard stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Data viewing endpoints
@app.get("/customers")
def list_customers(limit: int = 50, db: Session = Depends(get_db)):
    """
    Get list of all customers with summary information
    """
    customers = db.query(Customer).order_by(Customer.created_at.desc()).limit(limit).all()
    
    return {
        "count": len(customers),
        "customers": [
            {
                "id": c.id,
                "name": f"{c.first_name or ''} {c.last_name or ''}".strip() or "Unknown",
                "email": c.email,
                "phone": c.phone,
                "whatsapp_phone": c.whatsapp_phone,
                "orders": c.order_count,
                "total_spent": float(c.total_orders),
                "created_at": c.created_at.isoformat()
            }
            for c in customers
        ]
    }

@app.get("/customers/{customer_id}")
def get_customer_details(customer_id: str, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific customer
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get customer's orders
    orders = [
        {
            "id": o.id,
            "order_id": o.platform_order_id,
            "platform": o.platform,
            "total": float(o.total_price),
            "status": o.status,
            "date": o.order_date.isoformat(),
            "items": json.loads(o.items_json) if o.items_json else []
        }
        for o in customer.orders
    ]
    
    # Get customer's messages
    messages = [
        {
            "id": m.id,
            "direction": m.direction,
            "content": m.content,
            "channel": m.channel,
            "timestamp": (m.sent_at or m.received_at or m.created_at).isoformat(),
            "bot_handled": m.bot_handled
        }
        for m in customer.messages
    ]
    
    return {
        "customer": {
            "id": customer.id,
            "name": f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Unknown",
            "email": customer.email,
            "phone": customer.phone,
            "whatsapp_phone": customer.whatsapp_phone,
            "total_orders": float(customer.total_orders),
            "order_count": customer.order_count,
            "created_at": customer.created_at.isoformat()
        },
        "orders": orders,
        "messages": messages
    }

@app.get("/messages/recent")
def get_recent_messages(limit: int = 50, db: Session = Depends(get_db)):
    """
    Get recent messages across all customers
    """
    messages = db.query(Message).order_by(Message.created_at.desc()).limit(limit).all()
    
    return {
        "total": len(messages),
        "messages": [
            {
                "id": m.id,
                "customer_id": m.customer_id,
                "customer_name": f"{m.customer.first_name or ''} {m.customer.last_name or ''}".strip() or "Unknown",
                "direction": m.direction,
                "content": m.content,
                "channel": m.channel,
                "timestamp": (m.sent_at or m.received_at or m.created_at).isoformat(),
                "bot_handled": m.bot_handled
            }
            for m in messages
        ]
    }

@app.get("/orders/recent")
def get_recent_orders(limit: int = 20, db: Session = Depends(get_db)):
    """
    Get recent orders across all customers
    """
    orders = db.query(Order).order_by(Order.created_at.desc()).limit(limit).all()
    
    return {
        "total": len(orders),
        "orders": [
            {
                "id": o.id,
                "order_id": o.platform_order_id,
                "customer_name": f"{o.customer.first_name or ''} {o.customer.last_name or ''}".strip() or "Unknown",
                "customer_email": o.customer.email,
                "platform": o.platform,
                "total": float(o.total_price),
                "status": o.status,
                "date": o.order_date.isoformat(),
                "items": json.loads(o.items_json) if o.items_json else []
            }
            for o in orders
        ]
    }


# Add these new endpoints after existing ones

@app.post("/send-interactive")
def send_interactive_message(request: InteractiveMessageRequest, db: Session = Depends(get_db)):
    """
    Send message with interactive buttons
    """
    if not whatsapp_service:
        raise HTTPException(status_code=503, detail="WhatsApp service not available")
    
    try:
        result = whatsapp_service.send_interactive_buttons(
            request.phone, 
            request.message, 
            request.buttons
        )
        
        if result['status'] == 'sent':
            # Save to database
            customer = find_or_create_customer(db=db, whatsapp_phone=request.phone)
            
            outbound_msg = Message(
                customer_id=customer.id,
                channel="whatsapp",
                direction="outbound",
                content=request.message,
                platform_message_id=result['message_id'],
                sent_at=datetime.utcnow(),
                bot_handled=False,
                metadata_json=json.dumps({
                    "message_type": "interactive_buttons",
                    "buttons": request.buttons
                })
            )
            db.add(outbound_msg)
            db.commit()
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send-menu")
def send_menu_message(request: MenuMessageRequest, db: Session = Depends(get_db)):
    """
    Send menu message
    """
    if not whatsapp_service:
        raise HTTPException(status_code=503, detail="WhatsApp service not available")
    
    try:
        result = whatsapp_service.send_menu_message(
            request.phone,
            request.title,
            request.menu_items
        )
        
        if result['status'] == 'sent':
            customer = find_or_create_customer(db=db, whatsapp_phone=request.phone)
            
            outbound_msg = Message(
                customer_id=customer.id,
                channel="whatsapp",
                direction="outbound",
                content=f"{request.title}\n\nMenu sent with {len(request.menu_items)} options",
                platform_message_id=result['message_id'],
                sent_at=datetime.utcnow(),
                bot_handled=False,
                metadata_json=json.dumps({
                    "message_type": "menu",
                    "title": request.title,
                    "menu_items": request.menu_items
                })
            )
            db.add(outbound_msg)
            db.commit()
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/broadcast")
def send_broadcast(request: BroadcastRequest, db: Session = Depends(get_db)):
    """
    Send broadcast message to customer segments
    """
    if not whatsapp_service:
        raise HTTPException(status_code=503, detail="WhatsApp service not available")
    
    try:
        # Get customers based on segments
        customers = []
        
        if not request.customer_segments or "all" in request.customer_segments:
            # All customers with WhatsApp
            customers = db.query(Customer).filter(
                Customer.whatsapp_phone.isnot(None)
            ).all()
        else:
            # Specific segments
            if "vip" in request.customer_segments:
                vip_customers = db.query(Customer).filter(
                    Customer.order_count >= 3,
                    Customer.whatsapp_phone.isnot(None)
                ).all()
                customers.extend(vip_customers)
            
            if "new" in request.customer_segments:
                new_customers = db.query(Customer).filter(
                    Customer.order_count == 0,
                    Customer.whatsapp_phone.isnot(None)
                ).all()
                customers.extend(new_customers)
        
        # Remove duplicates
        unique_customers = {c.id: c for c in customers}.values()
        phone_list = [c.whatsapp_phone for c in unique_customers if c.whatsapp_phone]
        
        if not phone_list:
            return {"status": "error", "message": "No customers found for selected segments"}
        
        # Send broadcast
        result = whatsapp_service.broadcast_message(phone_list, request.message)
        
        # Log broadcast in database
        for customer in unique_customers:
            if customer.whatsapp_phone in result['results']['successful']:
                broadcast_msg = Message(
                    customer_id=customer.id,
                    channel="whatsapp",
                    direction="outbound",
                    content=request.message,
                    sent_at=datetime.utcnow(),
                    bot_handled=False,
                    metadata_json=json.dumps({
                        "message_type": "broadcast",
                        "segments": request.customer_segments
                    })
                )
                db.add(broadcast_msg)
        
        db.commit()
        
        return {
            "status": "success",
            "total_customers": len(unique_customers),
            "broadcast_result": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/customers/segments")
def get_customer_segments(db: Session = Depends(get_db)):
    """
    Get customer segment statistics
    """
    try:
        total_customers = db.query(Customer).count()
        whatsapp_customers = db.query(Customer).filter(
            Customer.whatsapp_phone.isnot(None)
        ).count()
        
        vip_customers = db.query(Customer).filter(
            Customer.order_count >= 3
        ).count()
        
        new_customers = db.query(Customer).filter(
            Customer.order_count == 0
        ).count()
        
        return {
            "segments": {
                "all": {
                    "total": total_customers,
                    "whatsapp_enabled": whatsapp_customers
                },
                "vip": {
                    "total": vip_customers,
                    "description": "Customers with 3+ orders"
                },
                "new": {
                    "total": new_customers,
                    "description": "Customers with 0 orders"
                }
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
def detect_user_choice(message_text: str, options_count: int) -> Optional[int]:
    """
    Detect if user selected a numbered option
    Returns option number (1-based) or None
    """
    text = message_text.strip()
    
    # Check if message is just a number
    if text.isdigit():
        choice = int(text)
        if 1 <= choice <= options_count:
            return choice
    
    # Check for number at start of message
    if len(text) > 0 and text[0].isdigit():
        choice = int(text[0])
        if 1 <= choice <= options_count:
            return choice
    
    return None

def handle_main_menu_selection(choice: int, customer: Customer, db: Session) -> str:
    """
    Handle main menu selections
    """
    if choice == 1:  # My Orders
        return handle_orders_request(customer, db)
    elif choice == 2:  # Products
        return handle_products_request(customer, db)
    elif choice == 3:  # Support
        return f"Hi {customer.first_name or 'there'}! 🆘\n\nI'm here to help! You can ask me about:\n• Order issues\n• Product questions\n• Returns & refunds\n• Account problems\n\nWhat do you need help with?"
    elif choice == 4:  # Account
        return handle_account_request(customer, db)
    else:
        return "Sorry, I didn't understand that choice. Please reply with 1, 2, 3, or 4."

def handle_orders_request(customer: Customer, db: Session) -> str:
    """
    Handle order status requests
    """
    recent_orders = db.query(Order).filter(
        Order.customer_id == customer.id
    ).order_by(Order.order_date.desc()).limit(5).all()
    
    if not recent_orders:
        return f"Hi {customer.first_name or 'there'}! 📦\n\nI don't see any orders for you yet. Ready to place your first order? Check out our products!"
    
    orders_text = f"*Your Recent Orders* 📦\n\n"
    for i, order in enumerate(recent_orders, 1):
        status_emoji = "✅" if order.status == "delivered" else "🚚" if order.status == "shipped" else "⏳"
        orders_text += f"{i}. Order {order.platform_order_id}\n"
        orders_text += f"   {status_emoji} {order.status.title()}\n"
        orders_text += f"   💰 ${order.total_price}\n"
        orders_text += f"   📅 {order.order_date.strftime('%b %d, %Y')}\n\n"
    
    return orders_text + "Need help with any of these orders? Just ask!"

def handle_products_request(customer: Customer, db: Session) -> str:
    """
    Show product catalog
    """
    # Simple product catalog (in real app, this would come from database)
    products = [
        {"name": "Wireless Headphones", "price": 99.99, "id": "WH001"},
        {"name": "Bluetooth Speaker", "price": 79.99, "id": "BS002"},
        {"name": "Phone Case", "price": 24.99, "id": "PC003"},
        {"name": "Charging Cable", "price": 19.99, "id": "CC004"},
        {"name": "Power Bank", "price": 49.99, "id": "PB005"}
    ]
    
    catalog_text = f"*Our Products* 🛍️\n\n"
    for i, product in enumerate(products, 1):
        catalog_text += f"{i}. *{product['name']}*\n"
        catalog_text += f"   💰 ${product['price']}\n"
        catalog_text += f"   🆔 {product['id']}\n\n"
    
    catalog_text += "Interested in any product? Just tell me the name or number!"
    return catalog_text

def handle_account_request(customer: Customer, db: Session) -> str:
    """
    Show account information
    """
    account_text = f"*Your Account* 👤\n\n"
    account_text += f"📝 Name: {customer.first_name or 'Not set'} {customer.last_name or ''}\n"
    account_text += f"📧 Email: {customer.email or 'Not set'}\n"
    account_text += f"📱 Phone: {customer.whatsapp_phone or customer.phone or 'Not set'}\n"
    account_text += f"🛒 Total Orders: {customer.order_count}\n"
    account_text += f"💰 Total Spent: ${customer.total_orders:.2f}\n"
    account_text += f"📅 Customer Since: {customer.created_at.strftime('%B %Y')}\n\n"
    
    if customer.order_count >= 3:
        account_text += "⭐ *VIP Customer Status* - Thank you for your loyalty!\n\n"
    
    account_text += "Need to update any information? Just let me know!"
    return account_text

# Business logic functions
def generate_response(message_text: str, customer: Customer, db: Session) -> str:
    """
    Enhanced response generation with interactive menus
    """
    text = message_text.lower().strip()
    name = customer.first_name or "there"
    
    # Check if user is responding to main menu
    menu_choice = detect_user_choice(message_text, 4)  # 4 menu options
    if menu_choice:
        return handle_main_menu_selection(menu_choice, customer, db)
    
    # Greeting or menu request
    if any(word in text for word in ["hi", "hello", "hey", "menu", "start", "help"]):
        return f"Hi {name}! 👋 Welcome!\n\nWhat can I help you with today?\n\n1. 📦 My Orders\n2. 🛍️ Products\n3. 🆘 Support\n4. 👤 My Account\n\nReply with the number of your choice."
    
    # Direct order status requests
    elif any(word in text for word in ["order", "status", "track", "shipping"]):
        return handle_orders_request(customer, db)
    
    # Product inquiries
    elif any(word in text for word in ["product", "catalog", "buy", "shop", "price"]):
        return handle_products_request(customer, db)
    
    # Account requests
    elif any(word in text for word in ["account", "profile", "info", "details"]):
        return handle_account_request(customer, db)
    
    # Return/refund requests
    elif any(word in text for word in ["return", "refund", "exchange", "cancel"]):
        return f"Hi {name}! I can help with returns. 🔄\n\n1. ✅ Yes, start return process\n2. ❌ No, just asking\n\nWhich option applies to you?"
    
    # Thank you
    elif any(word in text for word in ["thank", "thanks", "appreciate"]):
        return f"You're welcome, {name}! 😊\n\nAnything else I can help with? Type 'menu' to see all options."
    
    # Default - show menu
    else:
        return f"Thanks for your message, {name}! 💬\n\nI want to help you properly. Here's what I can do:\n\n1. 📦 Check Orders\n2. 🛍️ Browse Products\n3. 🆘 Get Support\n4. 👤 Account Info\n\nReply with a number or type 'menu' anytime!"

def trigger_simple_automations(customer: Customer, order: Order) -> List[str]:
    """
    Trigger simple automation workflows based on customer and order data
    """
    actions = []
    
    # First-time customer welcome
    if customer.order_count == 1:
        actions.append("welcome_new_customer")
        logger.info(f"🎉 New customer welcome triggered: {customer.first_name} (${order.total_price})")
    
    # High-value order processing
    if order.total_price > 100:
        actions.append("high_value_order_alert")
        logger.info(f"💰 High value order detected: ${order.total_price} from {customer.first_name}")
    
    # VIP customer recognition (3+ orders)
    if customer.order_count >= 3:
        actions.append("vip_customer_recognition")
        logger.info(f"⭐ VIP customer activity: {customer.first_name} (Order #{customer.order_count})")
    
    # Large order special handling
    if order.total_price > 500:
        actions.append("premium_order_handling")
        logger.info(f"💎 Premium order detected: ${order.total_price} - Special handling activated")
    
    # Returning customer appreciation
    if customer.order_count > 1 and customer.order_count < 3:
        actions.append("returning_customer_thanks")
        logger.info(f"🔄 Returning customer: {customer.first_name} (Order #{customer.order_count})")
    
    return actions

# Development and testing endpoints
@app.get("/test/webhook-data")
def get_test_webhook_data():
    """
    Get sample webhook data for testing
    """
    return {
        "whatsapp_message": {
            "message_id": "wamid_test_123",
            "from_phone": "+1234567890",
            "message_text": "Hi, what's my order status?",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "customer_name": "Test Customer"
        },
        "shopify_order": {
            "order_id": "TEST-ORDER-001",
            "customer_email": "test@example.com",
            "total_price": 99.99,
            "order_status": "pending",
            "items": [
                {"product": "Test Product", "quantity": 2, "price": 49.99}
            ],
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
    }

@app.post("/test/simulate-customer-journey")
def simulate_customer_journey(db: Session = Depends(get_db)):
    """
    Simulate a complete customer journey for testing
    """
    try:
        # Step 1: Simulate Shopify order
        test_order = ShopifyOrder(
            order_id="SIM-001",
            customer_email="simulation@test.com",
            total_price=157.99,
            order_status="confirmed",
            items=[
                {"product_id": "123", "title": "Wireless Headphones", "quantity": 1, "price": 157.99}
            ],
            created_at=datetime.utcnow().isoformat() + "Z"
        )
        
        order_result = shopify_webhook(test_order, db)
        
        # Step 2: Simulate WhatsApp message
        test_message = WebhookMessage(
            message_id="sim_msg_001",
            from_phone="+1555000001",
            message_text="Hi, I just placed order SIM-001. When will it ship?",
            timestamp=datetime.utcnow().isoformat() + "Z",
            customer_name="Simulation User"
        )
        
        message_result = whatsapp_webhook_json(test_message, db)
        
        return {
            "simulation": "complete",
            "steps": [
                {"step": 1, "action": "order_placed", "result": order_result},
                {"step": 2, "action": "customer_inquiry", "result": message_result}
            ],
            "message": "Check /customers and /messages/recent to see the simulated data"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)