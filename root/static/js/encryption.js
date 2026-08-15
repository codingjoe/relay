/**
 * Client-side encryption module for relay.
 *
 * Wraps libsodium-wrappers (UMD, loaded as window.sodium) to provide key
 * derivation, key generation, sealed-box encryption, and body decryption.
 * Keys are never persisted, they live only in JavaScript variables for the
 * lifetime of the page.
 */
(function () {
  "use strict";

  const SALT_BYTES = 16; // crypto_pwhash_SALTBYTES
  const NONCE_BYTES = 24; // crypto_secretbox_NONCEBYTES

  async function init() {
    await sodium.ready;
  }

  async function deriveKEK(passphrase, salt) {
    return sodium.crypto_pwhash(
      32,
      passphrase,
      salt,
      sodium.crypto_pwhash.OPSLIMIT_INTERACTIVE,
      sodium.crypto_pwhash.MEMLIMIT_INTERACTIVE,
      sodium.crypto_pwhash.ALG_ARGON2ID13,
    );
  }

  function generateMasterKey() {
    return sodium.randombytes_buf(32);
  }

  function generateKeypair() {
    return sodium.crypto_box_keypair();
  }

  /**
   * Encrypt a key with a symmetric key (secretbox).
   * Returns base64(nonce + ciphertext).
   */
  function encryptSecretKey(key, masterKey) {
    const nonce = sodium.randombytes_buf(sodium.crypto_secretbox_NONCEBYTES);
    const encrypted = sodium.crypto_secretbox(key, nonce, masterKey);
    return toBase64(concat(nonce, encrypted));
  }

  /**
   * Decrypt a key from base64(nonce + ciphertext).
   */
  function decryptSecretKey(packed, masterKey) {
    const bytes = fromBase64(packed);
    const nonce = bytes.slice(0, NONCE_BYTES);
    const ciphertext = bytes.slice(NONCE_BYTES);
    return sodium.crypto_secretbox_open(ciphertext, nonce, masterKey);
  }

  /**
   * Encrypt the master key with a KEK.
   * Returns base64(salt + nonce + ciphertext).
   */
  function encryptMasterKey(masterKey, kek, salt) {
    const nonce = sodium.randombytes_buf(sodium.crypto_secretbox_NONCEBYTES);
    const encrypted = sodium.crypto_secretbox(masterKey, nonce, kek);
    return toBase64(concat(salt, nonce, encrypted));
  }

  /**
   * Decrypt the master key from base64(salt + nonce + ciphertext).
   * Returns { masterKey, salt }.
   */
  function decryptMasterKey(packed, passphrase) {
    const bytes = fromBase64(packed);
    const salt = bytes.slice(0, SALT_BYTES);
    const nonce = bytes.slice(SALT_BYTES, SALT_BYTES + NONCE_BYTES);
    const ciphertext = bytes.slice(SALT_BYTES + NONCE_BYTES);
    return deriveKEK(passphrase, salt).then((kek) => ({
      masterKey: sodium.crypto_secretbox_open(ciphertext, nonce, kek),
      salt,
    }));
  }

  function seal(plaintext, publicKey) {
    return sodium.crypto_box_seal(plaintext, publicKey);
  }

  function unseal(sealed, privateKey) {
    return sodium.crypto_box_seal_open(sealed, privateKey);
  }

  /**
   * Decrypt a message body stored as nonce + ciphertext (concatenated).
   */
  function decryptBody(packed, fileKey) {
    const nonce = packed.slice(0, NONCE_BYTES);
    const ciphertext = packed.slice(NONCE_BYTES);
    return sodium.crypto_secretbox_open(ciphertext, nonce, fileKey);
  }

  function toBase64(bytes) {
    return sodium.to_base64(bytes, sodium.base64_variants.ORIGINAL);
  }

  function fromBase64(str) {
    return sodium.from_base64(str, sodium.base64_variants.ORIGINAL);
  }

  async function fingerprint(publicKey) {
    const hashBuffer = await crypto.subtle.digest("SHA-256", publicKey);
    const hashArray = new Uint8Array(hashBuffer);
    return Array.from(hashArray.slice(0, 8))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }

  function concat(...arrays) {
    const total = arrays.reduce((sum, a) => sum + a.length, 0);
    const result = new Uint8Array(total);
    let offset = 0;
    for (const a of arrays) {
      result.set(a, offset);
      offset += a.length;
    }
    return result;
  }

  window.relayEncryption = {
    init,
    deriveKEK,
    generateMasterKey,
    generateKeypair,
    encryptMasterKey,
    decryptMasterKey,
    encryptSecretKey,
    decryptSecretKey,
    seal,
    unseal,
    decryptBody,
    toBase64,
    fromBase64,
    fingerprint,
    SALT_BYTES,
    NONCE_BYTES,
  };
})();
