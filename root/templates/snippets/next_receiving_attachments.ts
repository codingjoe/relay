// app/api/email/route.ts
import PostalMime from "postal-mime";
import { Webhook } from "standardwebhooks";

const webhook = new Webhook(process.env.WEBHOOK_SIGNING_SECRET!);

export async function POST(req: Request) {
  const raw = await req.text();
  webhook.verify(raw, Object.fromEntries(req.headers));
  const event = JSON.parse(raw); // type == email.received
  const body = await fetch(event.body_url).then((res) => res.arrayBuffer());
  const email = await PostalMime.parse(body);
  const invoice = email.attachments.find((file) => file.mimeType === "application/pdf");
  return new Response(null, { status: 204 });
}
