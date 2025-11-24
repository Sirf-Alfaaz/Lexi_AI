# AI Legal Companion

A comprehensive legal document processing and research platform powered by AI, featuring document summarization, legal research, document generation, risk analysis, and more.

## Features

- 📄 **Document Processing**: Upload PDFs or enter text for analysis
- 🔍 **Legal Research**: AI-powered legal research assistant
- 📝 **Document Generation**: Generate various legal documents (rent agreements, NDAs, service agreements, etc.)
- ⚠️ **Risk Analysis**: Analyze contracts for potential risks
- ✅ **Document Review**: Check documents for completeness and correctness
- 📊 **Admin Dashboard**: Comprehensive admin panel with user management and analytics
- 🔐 **Secure Authentication**: JWT-based authentication with email verification (OTP)
- 📧 **Email Integration**: OTP verification via email

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **MongoDB** - NoSQL database (MongoDB Atlas)
- **Motor** - Async MongoDB driver
- **Google Gemini AI** - AI model for legal document processing
- **PyMuPDF** - PDF processing
- **ReportLab** - PDF generation
- **JWT** - Authentication tokens
- **Bcrypt** - Password hashing

### Frontend
- **React** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool

## Project Structure

```
Major_1/
├── backend/
│   ├── main.py              # FastAPI application
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.tsx         # Main React component
│   │   └── ...
│   └── package.json         # Node dependencies
└── README.md
```

## Setup Instructions

### Prerequisites
- Python 3.8+
- Node.js 16+
- MongoDB Atlas account (or local MongoDB)

### Backend Setup

1. **Navigate to backend directory:**
   ```bash
   cd backend
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   ```

3. **Activate virtual environment:**
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure environment variables:**
   Create a `.env` file in the `backend` directory:
   ```env
   # MongoDB Configuration
   MONGODB_URL=mongodb+srv://username:ENCODED_PASSWORD@cluster.mongodb.net/legal_db?retryWrites=true&w=majority
   MONGODB_DB_NAME=legal_db
   
   # Gemini AI API Key
   GEMINI_API_KEY=your_gemini_api_key_here
   
   # JWT Configuration
   JWT_EXPIRE_MINUTES=60
   
   # Email Configuration (optional)
   EMAIL_ENABLED=false
   EMAIL_SERVICE=gmail
   EMAIL_FROM=noreply@yourdomain.com
   EMAIL_PASSWORD=your_email_password
   EMAIL_SMTP_SERVER=smtp.gmail.com
   EMAIL_SMTP_PORT=587
   EMAIL_USE_TLS=true
   ```

   **Important:** URL-encode special characters in your MongoDB password:
   - `!` → `%21`
   - `@` → `%40`
   - `#` → `%23`
   - etc.

6. **Run the server:**
   ```bash
   uvicorn main:app --reload
   ```

   Server will start at `http://127.0.0.1:8000`

### Frontend Setup

1. **Navigate to frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Start development server:**
   ```bash
   npm run dev
   ```

   Frontend will start at `http://localhost:5173`

## MongoDB Setup

### MongoDB Atlas (Cloud - Recommended)

1. Create a free cluster at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Get your connection string from: Cluster → Connect → Connect your application
3. Select **Python** driver, version **4.6 or later**
4. Copy the connection string and update your `.env` file
5. **Whitelist your IP address:**
   - Go to Network Access → Add IP Address
   - Add `0.0.0.0/0` for development (or your specific IP)
6. **Verify database user:**
   - Go to Database Access
   - Ensure user has "Read and write to any database" permissions

### Local MongoDB

1. Install MongoDB locally
2. Start MongoDB service
3. Use connection string: `mongodb://localhost:27017/legal_db`

## API Endpoints

### Authentication
- `POST /auth/login` - User login
- `POST /auth/register` - User registration (requires OTP)
- `POST /auth/send-otp` - Send OTP for email verification
- `POST /auth/verify-otp` - Verify OTP
- `POST /auth/refresh` - Refresh access token

### Document Processing
- `POST /process` - Process documents (summarize, research, generate, check, analyze-risk)

### Admin (Requires Admin Token)
- `GET /admin/stats` - Get admin statistics
- `GET /admin/users` - Get users list
- `POST /admin/users/create` - Create new user (bypasses OTP)
- `POST /admin/users/create-admin` - Create admin user
- `DELETE /admin/users/{user_id}` - Delete user
- `PUT /admin/users/{user_id}/toggle-admin` - Toggle admin status

### Health & Debug
- `GET /health` - Health check
- `GET /debug/schema` - Database schema info

## Document Types Supported

- Rent Agreement
- Non-Disclosure Agreement (NDA)
- Service Agreement
- Employment Offer Letter
- Power of Attorney
- Marriage Certificate
- Sale Deed
- Affidavit
- Loan Agreement
- Partnership Agreement

## Languages Supported

- English (en)
- Hindi (hi)
- Bengali (bd)

## Development

### Backend Development
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Development
```bash
cd frontend
npm run dev
```

## Production Deployment

1. Set `EMAIL_ENABLED=true` in production
2. Use secure MongoDB connection with proper IP whitelisting
3. Set strong `SECRET_KEY` for JWT tokens
4. Configure proper CORS origins
5. Use environment variables for all sensitive data

## License

This project is proprietary software.

## Support

For issues or questions, please contact the development team.

