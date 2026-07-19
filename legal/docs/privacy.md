{% load i18n %}

# Privacy Policy

{% blocktranslate %}Last updated: {{ last_updated }}{% endblocktranslate %}

## 1. {% translate "overview"|title %}

{% blocktranslate %}{{ site_name }} collects and processes personal data in accordance with the General Data Protection Regulation (GDPR) and applicable data protection laws.{% endblocktranslate %}

## 2. {% translate "data we collect"|title %}

### {% translate "account data"|title %}

- {% translate "GitHub username and user ID" %}
- {% translate "email address from your GitHub account" %}

### {% translate "usage data"|title %}

- {% translate "domains you register and their DNS status" %}
- {% translate "SMTP credentials (hashed)" %}
- {% translate "message metadata: sender, recipient, subject, status" %}
- {% translate "IP addresses for spam prevention and abuse detection" %}

### {% translate "data we do not collect"|title %}

- {% blocktranslate %}We do not read, store, or process the content of your emails beyond what is necessary for delivery and spam detection.{% endblocktranslate %}

## 3. {% translate "legal basis"|title %}

{% blocktranslate %}Processing is based on Article 6(1)(b) GDPR (performance of a contract) and Article 6(1)(f) GDPR (legitimate interests in preventing abuse).{% endblocktranslate %}

## 4. {% translate "data retention"|title %}

{% blocktranslate %}Message metadata is retained for 30 days. Raw message bodies are stored only for the duration needed for delivery and are deleted immediately after successful delivery.{% endblocktranslate %}

## 5. {% translate "your rights"|title %}

- {% translate "right of access (Art. 15 GDPR)" %}
- {% translate "right to rectification (Art. 16 GDPR)" %}
- {% translate "right to erasure (Art. 17 GDPR)" %}
- {% translate "right to restriction of processing (Art. 18 GDPR)" %}
- {% translate "right to data portability (Art. 20 GDPR)" %}
- {% translate "right to object (Art. 21 GDPR)" %}

## 6. {% translate "contact"|title %}

{% blocktranslate %}To exercise your rights or for privacy inquiries, contact us at {{ contact_email }}.{% endblocktranslate %}
