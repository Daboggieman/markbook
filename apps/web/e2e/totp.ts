/**
 * Minimal RFC 6238 TOTP (30 s, SHA-1, 6 digits) over a base32 secret —
 * enough to enroll an MFA user through the real API in seeding, with zero
 * new dependencies. The API verifies with pyotp; this mirrors it.
 */
import crypto from "node:crypto";

const B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32Decode(input: string): Buffer {
  const clean = input.replace(/=+$/, "").toUpperCase();
  let bits = 0;
  let value = 0;
  const out: number[] = [];
  for (const ch of clean) {
    const idx = B32.indexOf(ch);
    if (idx < 0) continue;
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(out);
}

export function totpNow(secretB32: string, atSeconds: number = Math.floor(Date.now() / 1000)): string {
  const counter = Buffer.alloc(8);
  counter.writeUInt32BE(Math.floor(atSeconds / 30), 4);
  const hmac = crypto.createHmac("sha1", base32Decode(secretB32)).update(counter).digest();
  const offset = hmac[hmac.length - 1]! & 0x0f;
  const code =
    ((hmac[offset]! & 0x7f) << 24) |
    ((hmac[offset + 1]! & 0xff) << 16) |
    ((hmac[offset + 2]! & 0xff) << 8) |
    (hmac[offset + 3]! & 0xff);
  return String(code % 1_000_000).padStart(6, "0");
}
