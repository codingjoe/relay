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
