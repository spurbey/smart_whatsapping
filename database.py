"""
Database models and connection setup
This file defines how your data is structured in the database
"""

from sqlalchemy import create_engine, Column, String, Float, DateTime, Text, ForeignKey, Boolean, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timedelta, timezone
import uuid
import json

# Database connection string - replace with your actual database URL
DATABASE_URL = "postgresql://postgres:water000@localhost:5432/ecommerce_automation"

# Create database engine - this handles connections to PostgreSQL
engine = create_engine(DATABASE_URL)

# Create session factory - sessions handle individual database transactions  
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all database models
Base = declarative_base()

# Database Models - these define your table structures

class Customer(Base):
    """
    Customer table - stores customer information
    This is like defining the structure of a spreadsheet
    """
    __tablename__ = "customers"  # Actual table name in database
    
    # Primary key - unique identifier for each customer
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Customer contact information
    email = Column(String, unique=True, nullable=True)  # nullable=True means can be empty
    phone = Column(String, unique=True, nullable=True)
    whatsapp_phone = Column(String, nullable=True)
    telegram_id = Column(String, nullable=True)
    
    # Customer details
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    
    # Business metrics
    total_orders = Column(Float, default=0.0)  # Total amount spent
    order_count = Column(Float, default=0)     # Number of orders
    
    # Timestamps - track when records are created/updated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - these create connections to other tables
    orders = relationship("Order", back_populates="customer")  # One customer can have many orders
    messages = relationship("Message", back_populates="customer")  # One customer can have many messages
    cart_items = relationship("CartItem", back_populates="customer")
    activities = relationship("CustomerActivity", back_populates="customer")

class Order(Base):
    """
    Order table - stores order information from Shopify, WooCommerce, etc.
    """
    __tablename__ = "orders"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Foreign key - connects to customer table
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    
    # Order details
    platform_order_id = Column(String, nullable=False)  # Original order ID from Shopify/etc
    platform = Column(String, nullable=False)  # 'shopify', 'woocommerce', etc.
    
    # Financial information
    total_price = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    
    # Order status
    status = Column(String, nullable=False)  # 'pending', 'shipped', 'delivered', etc.
    fulfillment_status = Column(String, nullable=True)
    
    # Order content (stored as JSON text for simplicity)
    items_json = Column(Text, nullable=True)  # JSON string of order items
    
    # Timestamps
    order_date = Column(DateTime, nullable=False)  # When order was placed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship back to customer
    customer = relationship("Customer", back_populates="orders")

class Message(Base):
    """
    Message table - stores all customer communications
    """
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Foreign key to customer
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    
    # Message details
    channel = Column(String, nullable=False)  # 'whatsapp', 'telegram', 'email', etc.
    direction = Column(String, nullable=False)  # 'inbound' or 'outbound'
    content = Column(Text, nullable=False)  # The actual message text
    
    # Platform-specific IDs
    platform_message_id = Column(String, nullable=True)  # WhatsApp message ID, etc.
    
    # Message metadata (stored as JSON)
    metadata_json = Column(Text, nullable=True)  # Additional data like attachments, etc.
    
    # Workflow tracking
    workflow_id = Column(String, nullable=True)  # Which automation workflow sent this
    bot_handled = Column(Boolean, default=False)  # Was this handled by bot or human?
    
    # Timestamps
    sent_at = Column(DateTime, nullable=True)  # When message was sent (for outbound)
    received_at = Column(DateTime, nullable=True)  # When message was received (for inbound)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship back to customer
    customer = relationship("Customer", back_populates="messages")

class WebhookEvent(Base):
    """
    Webhook events table - logs all incoming webhooks for debugging
    """
    __tablename__ = "webhook_events"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Webhook details
    source = Column(String, nullable=False)  # 'shopify', 'whatsapp', etc.
    event_type = Column(String, nullable=False)  # 'order.created', 'message.received', etc.
    
    # Raw webhook data
    raw_data = Column(Text, nullable=False)  # Complete JSON payload
    
    # Processing status
    processed = Column(Boolean, default=False)
    processing_error = Column(Text, nullable=True)
    
    # Timestamps
    received_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

# Database helper functions


class Product(Base):
    '''
    prodcut table - stores product informatin
    '''

    __tablename__ = "products"

    id = Column(String, primary_key = True, default = lambda : str(uuid.uuid4()))

    #product basic info

    name  = Column(String, nullable = False)
    description = Column(Text, nullable = True)
    price = Column(Float, nullable = False)

    #Categories
    category = Column(String, nullable = False)  #  Electronics, Clothing, Home, etc.
    subcategory = Column(String, nullable = True)

    #inventory details
    sku = Column(String, unique = True, nullable = False)
    stock_quantity = Column(Integer, default = 0)

    # Additional fields
    image_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


    #relationships

    cart_items = relationship("CartItem", back_populates = "product")
    activities = relationship("CustomerActivity", back_populates="product")

class CartItem(Base):
    """
    Shopping cart items - tracks what customers add to cart (for abandonment detection)
    """
    __tablename__ = "cart_items"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Foreign keys
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    
    # Cart item details
    quantity = Column(Integer, nullable=False, default=1)
    price_at_time = Column(Float, nullable=False)  # Price when added to cart
    
    # Timestamps
    added_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    customer = relationship("Customer", back_populates="cart_items")
    product = relationship("Product", back_populates="cart_items")

class CustomerActivity(Base):
    """
    Customer browsing and interaction tracking
    """
    __tablename__ = "customer_activities"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Foreign keys
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=True)  # Some activities might not involve products
    
    # Activity details
    activity_type = Column(String, nullable=False)  # 'view_product', 'add_to_cart', 'remove_from_cart', etc.
    metadata_json = Column(Text, nullable=True)  # Store additional data as JSON
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships  
    customer = relationship("Customer", back_populates="activities")
    product = relationship("Product", back_populates="activities")



def get_database_session():
    """
    Create a database session for handling transactions
    Use this in your API endpoints to interact with the database
    """
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Session will be closed by the caller

def create_tables():
    """
    Create all tables in the database
    Run this once to set up your database schema
    """
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")

def drop_tables():
    """
    Delete all tables - useful for development/testing
    BE CAREFUL: This deletes all your data!
    """
    Base.metadata.drop_all(bind=engine)
    print("⚠️  All database tables dropped!")

# Database utility functions

def find_or_create_customer(db, email=None, phone=None, whatsapp_phone=None):
    """
    Find an existing customer or create a new one
    This prevents duplicate customers in your database
    """
    # Try to find existing customer by email or phone
    customer = None
    
    if email:
        customer = db.query(Customer).filter(Customer.email == email).first()
    
    if not customer and phone:
        customer = db.query(Customer).filter(Customer.phone == phone).first()
    
    if not customer and whatsapp_phone:
        customer = db.query(Customer).filter(Customer.whatsapp_phone == whatsapp_phone).first()
    
    # If no existing customer found, create new one
    if not customer:
        customer = Customer(
            email=email,
            phone=phone,
            whatsapp_phone=whatsapp_phone
        )
        db.add(customer)
        db.commit()  # Save to database
        db.refresh(customer)  # Get the saved version with ID
        print(f"✅ Created new customer: {customer.id}")
    
    return customer

def add_sample_products(db):
    """
    Add sample products to database for testing
    Call this once to populate product catalog
    """
    sample_products = [
        {
            "name": "Wireless Bluetooth Headphones",
            "description": "High-quality wireless headphones with noise cancellation",
            "price": 99.99,
            "category": "Electronics",
            "subcategory": "Audio",
            "sku": "WBH001",
            "stock_quantity": 50
        },
        {
            "name": "Smartphone Charging Cable",
            "description": "Fast charging USB-C cable compatible with most devices",
            "price": 19.99,
            "category": "Electronics", 
            "subcategory": "Accessories",
            "sku": "SCC002",
            "stock_quantity": 100
        },
        {
            "name": "Cotton T-Shirt",
            "description": "Comfortable 100% cotton t-shirt in various colors",
            "price": 24.99,
            "category": "Clothing",
            "subcategory": "Shirts",
            "sku": "CTS003",
            "stock_quantity": 75
        }
        # Add more products as needed
    ]
    
    for product_data in sample_products:
        # Check if product already exists
        existing = db.query(Product).filter(Product.sku == product_data['sku']).first()
        if not existing:
            product = Product(**product_data)
            db.add(product)
    
    db.commit()
    print(f"✅ Added {len(sample_products)} sample products")

def simulate_cart_abandonment(db, customer_id: str, product_id: str, quantity: int = 1):
    """
    Simulate a customer adding item to cart (for abandonment testing)
    """
    # Get product to get current price
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return None
    
    # Add to cart
    cart_item = CartItem(
        customer_id=customer_id,
        product_id=product_id,
        quantity=quantity,
        price_at_time=product.price
    )
    db.add(cart_item)
    
    # Log activity
    activity = CustomerActivity(
        customer_id=customer_id,
        product_id=product_id,
        activity_type="add_to_cart",
        metadata_json=json.dumps({"quantity": quantity, "price": product.price})
    )
    db.add(activity)
    
    db.commit()
    return cart_item

def get_abandoned_carts(db, hours_ago: int = 1):
    """
    Get carts abandoned more than X hours ago
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    
    abandoned_carts = db.query(CartItem).filter(
        CartItem.added_at <= cutoff_time
    ).all()
    
    return abandoned_carts
