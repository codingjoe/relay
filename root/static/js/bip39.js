/**
 * BIP39 mnemonic support for relay.
 *
 * Generates and decodes 12-word mnemonics (128 bits of entropy).
 * Uses the official BIP39 English wordlist loaded from CDN.
 * No full HD-wallet functionality, just entropy → words → entropy.
 */
(function () {
  "use strict";

  const ENTROPY_BITS = 128;
  const CHECKSUM_BITS = 4;
  const WORD_COUNT = 12;
  const WORDLIST_URL = "/static/js/bip39-wordlist.json";

  let wordlist = null;
  let wordMap = null;

  async function loadWordlist() {
    if (wordlist) return wordlist;
    const response = await fetch(WORDLIST_URL);
    wordlist = await response.json();
    wordMap = {};
    for (let i = 0; i < wordlist.length; i++) {
      wordMap[wordlist[i]] = i;
    }
    return wordlist;
  }

  /**
   * Generate a 12-word mnemonic from 128 bits of random entropy.
   * Returns an array of 12 words.
   */
  async function generateMnemonic() {
    await sodium.ready;
    const wordlist = await loadWordlist();
    const entropy = sodium.randombytes_buf(ENTROPY_BITS / 8);

    // Compute checksum: first 4 bits of SHA-256(entropy).
    const hashBuffer = await crypto.subtle.digest("SHA-256", entropy);
    const checksumByte = new Uint8Array(hashBuffer)[0];

    // Combine entropy + checksum bits.
    // 128 bits entropy + 4 bits checksum = 132 bits = 16.5 bytes.
    // We need to split into 11-bit groups for word indices.
    const bits = [];
    for (let i = 0; i < entropy.length; i++) {
      for (let j = 7; j >= 0; j--) {
        bits.push((entropy[i] >> j) & 1);
      }
    }
    for (let j = 7; j >= 4; j--) {
      bits.push((checksumByte >> j) & 1);
    }

    // Split into 11-bit groups.
    const words = [];
    for (let i = 0; i < WORD_COUNT; i++) {
      let index = 0;
      for (let j = 0; j < 11; j++) {
        index = (index << 1) | bits[i * 11 + j];
      }
      words.push(wordlist[index]);
    }
    return words;
  }

  /**
   * Decode a 12-word mnemonic back to entropy bytes.
   * Returns a Uint8Array of 16 bytes, or null if invalid.
   */
  async function mnemonicToEntropy(words) {
    await sodium.ready;
    const wordlist = await loadWordlist();

    if (words.length !== WORD_COUNT) return null;

    // Convert words to 11-bit indices.
    const bits = [];
    for (const word of words) {
      const index = wordMap[word];
      if (index === undefined) return null;
      for (let j = 10; j >= 0; j--) {
        bits.push((index >> j) & 1);
      }
    }

    // First 128 bits = entropy, last 4 bits = checksum.
    const entropy = new Uint8Array(ENTROPY_BITS / 8);
    for (let i = 0; i < entropy.length; i++) {
      let byte = 0;
      for (let j = 0; j < 8; j++) {
        byte = (byte << 1) | bits[i * 8 + j];
      }
      entropy[i] = byte;
    }

    // Verify checksum using SHA-256 (BIP39 standard).
    const hashBuffer = await crypto.subtle.digest("SHA-256", entropy);
    const checksumByte = new Uint8Array(hashBuffer)[0];
    for (let j = 7; j >= 4; j--) {
      const expected = (checksumByte >> j) & 1;
      const actual = bits[ENTROPY_BITS + (7 - j)];
      if (expected !== actual) return null;
    }

    return entropy;
  }

  /**
   * Encrypt the org private key with a KEK derived from the mnemonic entropy.
   * Returns base64(salt + nonce + ciphertext).
   */
  async function sealRecoveryKey(orgPrivateKey, entropy) {
    await sodium.ready;
    const salt = sodium.randombytes_buf(16);
    const kek = sodium.crypto_pwhash(
      32,
      sodium.to_base64(entropy, sodium.base64_variants.ORIGINAL),
      salt,
      sodium.crypto_pwhash.OPSLIMIT_INTERACTIVE,
      sodium.crypto_pwhash.MEMLIMIT_INTERACTIVE,
      sodium.crypto_pwhash.ALG_ARGON2ID13,
    );
    const nonce = sodium.randombytes_buf(sodium.crypto_secretbox_NONCEBYTES);
    const ciphertext = sodium.crypto_secretbox(orgPrivateKey, nonce, kek);
    return sodium.to_base64(
      new Uint8Array([...salt, ...nonce, ...ciphertext]),
      sodium.base64_variants.ORIGINAL,
    );
  }

  window.relayEntropy = {
    generateMnemonic,
    mnemonicToEntropy,
    sealRecoveryKey,
    toBase64: (bytes) =>
      sodium.to_base64(bytes, sodium.base64_variants.ORIGINAL),
    fromBase64: (str) =>
      sodium.from_base64(str, sodium.base64_variants.ORIGINAL),
  };
})();
