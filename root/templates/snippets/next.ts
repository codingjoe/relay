import nodemailer from "nodemailer";

const transport = nodemailer.createTransport({
  host: "smtp.relay.example.com",
  port: 465,
  secure: true,
  auth: { user: "acme", pass: "<credential key>" },
});

await transport.sendMail({
  from: "billing@acme.com",
  to: "kim@example.net",
  subject: "Invoice 42",
  text: "Attached.",
});


// app/api/email/route.ts: receive inbound email via standard webhooks
import { Webhook } from "standardwebhooks";

export async function POST(req: Request) {
  const raw = await req.text();
  new Webhook("<whsec_...>").verify(raw, Object.fromEntries(req.headers));
  const event = JSON.parse(raw); // type == email.received
  // download event.body_url
  return new Response(null, { status: 204 });
}
