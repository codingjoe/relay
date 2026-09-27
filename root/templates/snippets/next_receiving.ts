// app/api/email/route.ts
import { Webhook } from "standardwebhooks";

export async function POST(req: Request) {
  const raw = await req.text();
  new Webhook("<whsec_...>").verify(raw, Object.fromEntries(req.headers));
  const event = JSON.parse(raw); // type == email.received
  // download event.body_url
  return new Response(null, { status: 204 });
}
