import { ApiError, get, post, request } from './client';

export interface User {
  id: string;
  email: string;
  email_verified: boolean;
}

interface Message {
  message: string;
}

/** The signed-in user, or null when there is no session. */
export async function fetchMe(): Promise<User | null> {
  try {
    return await get<User>('auth', '/me');
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}

export const signup = (email: string, password: string) =>
  post<Message>('auth', '/signup', { email, password });

export const verifyEmail = (token: string, password: string, rememberMe: boolean) =>
  post<User>('auth', '/verify-email', { token, password, remember_me: rememberMe });

export const resendVerification = (email: string) =>
  post<Message>('auth', '/verify-email/resend', { email });

export const login = (email: string, password: string, rememberMe: boolean) =>
  post<User>('auth', '/login', { email, password, remember_me: rememberMe });

export const logout = () => request<null>('auth', '/logout', { method: 'POST' });

export const forgotPassword = (email: string) =>
  post<Message>('auth', '/password/forgot', { email });

export const resetPassword = (token: string, password: string) =>
  post<Message>('auth', '/password/reset', { token, password });
