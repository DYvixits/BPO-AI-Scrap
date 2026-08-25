import { apiRequest } from "@/services/api";
import type { Me, TokenPair } from "@/types/api";

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export function register(input: RegisterInput) {
  return apiRequest<TokenPair>("/auth/register", { method: "POST", body: input, auth: false });
}

export function login(input: LoginInput) {
  return apiRequest<TokenPair>("/auth/login", { method: "POST", body: input, auth: false });
}

export function fetchMe() {
  return apiRequest<Me>("/auth/me");
}
