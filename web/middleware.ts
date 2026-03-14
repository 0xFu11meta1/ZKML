import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";

// Routes that require authentication
const AUTH_PROTECTED = [
  "/settings",
  "/profile",
  "/evaluate",
  "/organizations",
  "/admin",
  "/api-keys",
];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Auth check for protected routes
  const isProtected = AUTH_PROTECTED.some(
    (route) => pathname === route || pathname.startsWith(route + "/"),
  );

  if (isProtected) {
    const token = await getToken({
      req: request,
      secret: process.env.NEXTAUTH_SECRET,
    });
    if (!token) {
      const signInUrl = new URL("/auth/signin", request.url);
      signInUrl.searchParams.set("callbackUrl", pathname);
      return NextResponse.redirect(signInUrl);
    }
  }

  // Generate CSP nonce for every response
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Build CSP header
  const csp = [
    `default-src 'self'`,
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    `style-src 'self' 'nonce-${nonce}'`,
    `img-src 'self' data: https:`,
    `connect-src 'self' ${apiUrl}`,
    `font-src 'self' data:`,
    `frame-ancestors 'none'`,
  ].join("; ");

  const response = NextResponse.next();

  // Set CSP and nonce header (consumed by Next.js <Script> components)
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("x-nonce", nonce);

  // Additional security headers
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=()",
  );

  return response;
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public assets
     */
    "/((?!_next/static|_next/image|favicon\\.ico|.*\\.svg$).*)",
  ],
};
