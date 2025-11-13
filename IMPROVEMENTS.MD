# Scribe - Code Quality Improvements

> Comprehensive review and recommendations for the Scribe codebase

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Frontend Improvements](#frontend-improvements)
4. [Backend Improvements](#backend-improvements)
5. [Security & Environment](#security-environment)
6. [Type System](#type-system)
7. [Project Structure](#project-structure)
8. [Prioritized Action Plan](#action-plan)

---

## Executive Summary

**Project:** Scribe - Cold email generation platform for research outreach

**Tech Stack:**
- **Frontend:** Next.js 15, React 19, TypeScript, Tailwind CSS, shadcn/ui
- **Backend:** Python, FastAPI
- **Database:** Supabase/PostgreSQL
- **Authentication:** Supabase Auth

**Overall Assessment:** Functional MVP with good foundation, needs architectural improvements for scalability.

**Key Areas for Improvement:**
- Frontend: State management, error boundaries, type safety
- Backend: Database service layer, API documentation, validation
- Shared: Security (environment variables), centralized type definitions

---

## Architecture Overview

### Backend-First Architecture

**This application follows a BACKEND-FIRST architecture:**

- ✅ **Frontend**: Only uses Supabase for authentication (OAuth, JWT)
- ✅ **Backend**: Handles ALL database operations with Supabase service role key
- ✅ **Security**: Backend validates JWT tokens and extracts user ID
- ✅ **No Direct Database Access**: Frontend NEVER queries Supabase database directly
- ✅ **API Communication**: All data flows through authenticated backend API endpoints

```
┌──────────────────────────────────────────────────────────────────┐
│                        Scribe Application                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────┐                                        │
│  │  Frontend            │                                        │
│  │  Next.js + React     │                                        │
│  └──────────┬───────────┘                                        │
│             │                                                    │
│             │ Auth Only                                          │
│             │              ┌──────────────────────┐              │
│             └─────────────▶│  Supabase Auth       │              │
│                            │  (Authentication)    │              │
│             ┌─────────────▶│                      │              │
│             │              └──────────────────────┘              │
│             │ All Data                                           │
│             │ Operations                                         │
│             │                                                    │
│             ▼                                                    │
│  ┌──────────────────────┐         ┌──────────────────────┐       │
│  │  Backend API         │────────▶│  Supabase Database   │       │
│  │  Python + FastAPI    │  Auth   │  PostgreSQL          │       │
│  │                      │  Token  │                      │       │
│  │  - Validates JWT     │         │  - Row Level         │       │
│  │  - Database ops      │         │    Security (RLS)    │       │
│  │  - Business logic    │         │  - Tables & indexes  │       │
│  └──────────────────────┘         └──────────────────────┘       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Responsibilities

**Frontend:**
- UI components and layouts
- Client-side state management
- Form validation and user interactions
- Supabase Auth integration (sign-in, sign-out, session management)
- API calls to backend for all data operations

**Backend:**
- JWT token validation
- All database operations (CRUD via Supabase client)
- Business logic and validation
- API endpoints
- Email generation service

---

## Frontend Improvements

### 1. State Management

**Current Issues:**
- Firebase config deleted - application broken
- Need to migrate to Supabase Auth
- Need to migrate all database operations to backend API endpoints
- Type safety problems (`any` types)
- localStorage management scattered

**Solution: Supabase Auth + API Client**

#### Setup Supabase Auth (Frontend)

**Create `config/supabase.ts`:**
```typescript
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables');
}

// Frontend client - ONLY for authentication
export const supabaseAuth = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
  },
});
```

**Frontend `.env.local`:**
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key_here
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

#### Create Auth Service

**Create `services/auth.service.ts`:**
```typescript
import { supabaseAuth } from '@/config/supabase';
import type { User } from '@supabase/supabase-js';

class AuthService {
  async signInWithGoogle() {
    const { data, error } = await supabaseAuth.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/dashboard`,
      },
    });
    if (error) throw error;
    return data;
  }

  async signOut() {
    const { error } = await supabaseAuth.auth.signOut();
    if (error) throw error;
  }

  async getSession() {
    const { data, error } = await supabaseAuth.auth.getSession();
    if (error) throw error;
    return data.session;
  }

  onAuthStateChange(callback: (user: User | null) => void) {
    return supabaseAuth.auth.onAuthStateChange((event, session) => {
      callback(session?.user ?? null);
    });
  }

  async getAuthToken(): Promise<string | null> {
    const { data: { session } } = await supabaseAuth.auth.getSession();
    return session?.access_token ?? null;
  }
}

export const authService = new AuthService();
```

#### Create API Client

**Create `services/api.ts`:**
```typescript
import { authService } from './auth.service';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export interface ApiError {
  message: string;
  status: number;
  details?: any;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async getHeaders(): Promise<HeadersInit> {
    const token = await authService.getAuthToken();
    return {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
    };
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const error: ApiError = {
        message: response.statusText,
        status: response.status,
      };
      try {
        const errorData = await response.json();
        error.details = errorData;
        error.message = errorData.message || error.message;
      } catch {}
      throw error;
    }
    return response.json();
  }

  async get<T>(endpoint: string, params?: Record<string, string>): Promise<T> {
    const url = new URL(`${this.baseUrl}${endpoint}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        url.searchParams.append(key, value);
      });
    }
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: await this.getHeaders(),
    });
    return this.handleResponse<T>(response);
  }

  async post<T>(endpoint: string, body: any): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers: await this.getHeaders(),
      body: JSON.stringify(body),
    });
    return this.handleResponse<T>(response);
  }

  async delete<T>(endpoint: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'DELETE',
      headers: await this.getHeaders(),
    });
    return this.handleResponse<T>(response);
  }
}

export const apiClient = new ApiClient(API_BASE_URL);

export const API_ENDPOINTS = {
  initUser: '/api/user/init',
  getUser: '/api/user/profile',
  getEmails: '/api/user/emails',
  generateEmail: '/api/generate-email',
  callOpenAI: '/api/call-openai',
} as const;
```

### 2. Custom Hooks

**Create `hooks/useAuth.ts`:**
```typescript
import { useState, useEffect } from 'react';
import { authService } from '@/services/auth.service';
import type { User } from '@supabase/supabase-js';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Get initial session
    authService.getSession().then(session => {
      setUser(session?.user ?? null);
      setLoading(false);
    });

    // Listen for auth changes
    const { data: { subscription } } = authService.onAuthStateChange(setUser);

    return () => subscription.unsubscribe();
  }, []);

  return {
    user,
    loading,
    isAuthenticated: !!user,
    signInWithGoogle: authService.signInWithGoogle,
    signOut: authService.signOut,
  };
}
```

**Create `hooks/useEmailHistory.ts`:**
```typescript
import { useState, useEffect } from 'react';
import { apiClient, API_ENDPOINTS } from '@/services/api';
import type { Email } from '@/types';

export function useEmailHistory() {
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEmails = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiClient.get<Email[]>(API_ENDPOINTS.getEmails);
      setEmails(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch emails');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEmails();
  }, []);

  return { emails, loading, error, refetch: fetchEmails };
}
```

### 3. Error Boundaries

**Create `components/shared/ErrorBoundary.tsx`:**
```typescript
"use client";

import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-center">
            <h2 className="text-2xl font-bold mb-4">Something went wrong</h2>
            <p className="text-gray-600 mb-4">{this.state.error?.message}</p>
            <button
              onClick={() => this.setState({ hasError: false })}
              className="px-4 py-2 bg-blue-500 text-white rounded"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
```

**Add to `app/layout.tsx`:**
```typescript
<ErrorBoundary>
  <AuthContextProvider>
    {children}
  </AuthContextProvider>
</ErrorBoundary>
```

---

## Backend Improvements

### Required API Endpoints

**Authentication Middleware:**
```python
# Validate Supabase JWT token
# Extract user_id from token
# Never trust user_id from request body
```

**API Endpoints:**

1. **POST /api/user/init** - Initialize user profile
   - Headers: `Authorization: Bearer {jwt_token}`
   - Body: `{ "name": string, "email": string }`
   - Return: User profile object

2. **GET /api/user/profile** - Get user profile
   - Headers: `Authorization: Bearer {jwt_token}`
   - Return: User profile object

3. **GET /api/user/emails** - Get email history
   - Headers: `Authorization: Bearer {jwt_token}`
   - Query: `?limit=50&offset=0`
   - Return: Array of email objects

4. **POST /api/generate-email** - Generate email
   - Headers: `Authorization: Bearer {jwt_token}`
   - Body: `{ "emailTemplate": string, "name": string, "interest": string }`
   - Return: `{ "email": string, "success": boolean }`

5. **POST /api/call-openai** - Generate template
   - Headers: `Authorization: Bearer {jwt_token}`
   - Body: `{ "prompt": string }`
   - Return: `{ "template": string }`

### Database Schema

```sql
-- Users table
CREATE TABLE users (
  id UUID REFERENCES auth.users PRIMARY KEY,
  email TEXT NOT NULL,
  "displayName" TEXT,
  "generationCount" INTEGER DEFAULT 0,
  "createdAt" TIMESTAMPTZ DEFAULT NOW()
);

-- Emails table
CREATE TABLE emails (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  "userId" UUID REFERENCES users(id) ON DELETE CASCADE,
  "recipientName" TEXT NOT NULL,
  "recipientInterest" TEXT NOT NULL,
  "emailMessage" TEXT NOT NULL,
  "createdAt" TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_emails_user_id ON emails("userId");
CREATE INDEX idx_emails_created_at ON emails("createdAt" DESC);

-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Backend can manage users" ON users
  FOR ALL USING (auth.role() = 'service_role' OR auth.uid() = id);

CREATE POLICY "Backend can manage emails" ON emails
  FOR ALL USING (auth.role() = 'service_role' OR auth.uid() = "userId");
```

---

## Security & Environment

### Frontend Environment (.env.local)

```env
# Supabase Auth (public - safe to expose)
# Modern Supabase API (2024+) - uses anon/publishable key for client-side auth
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key_here

# Backend API
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### Backend Environment (.env)

```env
# Supabase (Backend) - Modern API (2024+)
# Only need URL and service role key - JWT verification handled automatically via JWKS
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here

# External APIs
OPENAI_API_KEY=your_openai_api_key

# Application
ENVIRONMENT=development
```

**Security Best Practices:**
- ✅ Frontend uses publishable key (limited permissions, new system)
- ✅ Backend uses service role key (full permissions)
- ✅ Backend validates JWT tokens
- ✅ Never trust user ID from request body
- ✅ All sensitive credentials in `.env` files (gitignored)

---

## Type System

### Centralized Type Definitions

**`types/user.ts`:**
```typescript
export interface User {
  id: string;
  email: string;
  displayName: string | null;
  generationCount: number;
  createdAt: string;
}

export interface AuthContextType {
  user: User | null;
  loading: boolean;
  signOut: () => Promise<void>;
}
```

**`types/email.ts`:**
```typescript
export type EmailStatus = 'pending' | 'completed' | 'failed';

export interface Email {
  id: string;
  userId: string;
  recipientName: string;
  recipientInterest: string;
  emailMessage: string;
  createdAt: string;
}

export interface GenerationQueueItem {
  id: string;
  name: string;
  interest: string;
  status: EmailStatus;
}
```

**`types/api.ts`:**
```typescript
export interface GenerateEmailRequest {
  emailTemplate: string;
  name: string;
  interest: string;
}

export interface GenerateEmailResponse {
  email: string;
  success: boolean;
  error?: string;
}

export interface OpenAITemplateRequest {
  prompt: string;
}

export interface OpenAITemplateResponse {
  template: string;
}

export interface APIError {
  message: string;
  code?: string;
  status?: number;
  details?: any;
}
```

**`types/index.ts`:**
```typescript
export * from './user';
export * from './email';
export * from './api';
```

---

## Project Structure

```
/scribe
├── app/                        # Next.js App Router
│   ├── (auth)/                # Auth pages
│   │   └── page.tsx           # Login
│   ├── (dashboard)/           # Protected pages
│   │   ├── layout.tsx         # Dashboard layout
│   │   ├── page.tsx           # Main dashboard
│   │   ├── generate/          # Email generation
│   │   └── template/          # Template generation
│   ├── layout.tsx             # Root layout
│   ├── error.tsx              # Error handler
│   └── loading.tsx            # Loading state
│
├── components/
│   ├── ui/                    # shadcn components
│   ├── features/              # Feature components
│   │   ├── email/
│   │   └── auth/
│   ├── layout/                # Layout components
│   │   ├── Navbar.tsx
│   │   └── Header.tsx
│   └── shared/                # Shared components
│       ├── ErrorBoundary.tsx
│       └── ProtectedRoute.tsx
│
├── hooks/                     # Custom hooks
│   ├── useAuth.ts            # Auth state
│   ├── useUser.ts            # User profile
│   └── useEmailHistory.ts    # Email history
│
├── context/                   # React Context
│   ├── AuthContextProvider.tsx
│   └── EmailGenerationProvider.tsx
│
├── services/                  # API services
│   ├── api.ts                # Backend API client
│   ├── auth.service.ts       # Supabase Auth
│   └── index.ts
│
├── lib/                       # Utilities
│   ├── utils.ts              # General utilities
│   ├── validation.ts         # Form validation
│   ├── constants.ts          # App constants
│   └── errors.ts             # Error handling
│
├── types/                     # TypeScript types
│   ├── index.ts
│   ├── user.ts
│   ├── email.ts
│   └── api.ts
│
├── config/                    # Configuration
│   ├── supabase.ts           # Supabase client
│   └── constants.ts
│
├── .env.local                 # Environment variables
├── .env.example               # Example env file
└── package.json
```

---

## Prioritized Action Plan

### Phase 0: Supabase Setup (1-2 hours)
- [ ] Create Supabase project
- [ ] Set up database schema
- [ ] Configure Google OAuth
- [ ] Add environment variables

### Phase 1: Fix Broken State (2-3 hours)
- [ ] Create `config/supabase.ts` with auth client
- [ ] Remove all Firebase imports
- [ ] Create centralized type definitions
- [ ] Fix `any` types in AuthContext

### Phase 2: Service Layer (3-4 hours)
- [ ] Create `services/auth.service.ts`
- [ ] Create `services/api.ts` with API client
- [ ] Create custom hooks (useAuth, useEmailHistory)
- [ ] Update AuthContextProvider

### Phase 3: Backend API (4-5 hours)
- [ ] Add JWT verification middleware
- [ ] Implement user endpoints
- [ ] Update email generation endpoint
- [ ] Test all endpoints with auth

### Phase 4: Update Components (3-4 hours)
- [ ] Update login page to use Supabase Auth
- [ ] Update dashboard to use API hooks
- [ ] Update generate page
- [ ] Update template page

### Phase 5: Testing (2-3 hours)
- [ ] Test authentication flow
- [ ] Test email generation
- [ ] Test error scenarios
- [ ] Performance testing

### Phase 6: Cleanup (2-3 hours)
- [ ] Remove Firebase completely
- [ ] Add error boundaries
- [ ] Add loading states
- [ ] Improve error messages

### Phase 7: Code Quality (2-3 hours)
- [ ] Create utility functions
- [ ] Add JSDoc comments
- [ ] Clean up unused files
- [ ] Organize imports

**Total Estimated Time:** 20-30 hours

---

## Summary

### Key Improvements

1. **Backend-First Architecture**
   - All database operations through backend API
   - JWT token validation
   - Secure user authentication

2. **Type Safety**
   - Centralized type definitions
   - No `any` types
   - Type-safe API calls

3. **Service Layer**
   - Clean separation of concerns
   - Reusable API client
   - Proper error handling

4. **Modern Patterns**
   - Custom hooks for data fetching
   - Error boundaries
   - Loading states

### Next Steps

1. **Immediate**: Set up Supabase and fix broken imports
2. **This Week**: Complete service layer and hooks
3. **This Month**: Migrate all components and add error handling

This migration will transform your codebase from a working MVP to a professional, scalable application. Good luck! 🚀
