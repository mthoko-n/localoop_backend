from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.chat import chat_routes
from routers.login import auth_routes
from routers.notifications import notification_routes
from routers.profile import profile_routes
from src.database.mongo import connect_to_mongo, close_mongo_connection
from routers.location_search import user_location

# Lifespan function to manage MongoDB connection
async def lifespan(app: FastAPI):
    await connect_to_mongo()   # Connect to MongoDB on startup
    yield
    await close_mongo_connection()  # Close MongoDB on shutdown

# Create FastAPI app with lifespan
app = FastAPI(title="Localoop API", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat_routes.router, tags=["Chat"])
app.include_router(auth_routes.router, tags=["Authentication"]) 
# app.include_router(notification_routes.router, tags=["Notifications"])
app.include_router(profile_routes.router, tags=["Profile"])
app.include_router(user_location.router, tags=["User Locations"])