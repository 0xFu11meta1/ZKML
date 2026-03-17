/**
 * Development-only authentication helper.
 *
 * This module provides unsafe SHA-256 signing for local development and testing.
 * It MUST NEVER be used in production. The build process should ensure this module
 * is only loaded in development environments.
 *
 * In production, always require real Bittensor wallet signing via the browser extension.
 */

export async function signWithDevAuth(
  hotkey: string,
  nonce: string,
): Promise<string> {
  // Runtime guard: fail loudly in production
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "Development authentication is not available in production. " +
        "Use the Bittensor wallet extension for real signing.",
    );
  }

  const encoder = new TextEncoder();
  const data = encoder.encode(`${hotkey}:${nonce}`);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export const isDevelopmentAuth = () => {
  return (
    process.env.NEXT_PUBLIC_DEV_AUTH === "true" &&
    process.env.NODE_ENV !== "production"
  );
};
