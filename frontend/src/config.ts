// API Configuration
// This will use the environment variable at build time
// For local dev, create .env.local with: VITE_API_URL=http://127.0.0.1:8000
// For production (Render): https://lexi-ai-ct7h.onrender.com

export const API_URL = import.meta.env.VITE_API_URL || 'https://lexi-ai-ct7h.onrender.com';

// Helper function to build API endpoints
export const getApiUrl = (endpoint: string): string => {
  // Remove leading slash if present
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
  // Ensure API_URL doesn't have trailing slash
  const baseUrl = API_URL.endsWith('/') ? API_URL.slice(0, -1) : API_URL;
  return `${baseUrl}/${cleanEndpoint}`;
};


