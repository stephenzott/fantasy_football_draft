// Firebase web config for draft-day sync.
//
// HOW TO FILL THIS IN (one-time setup — see CLAUDE.md "Firebase setup"):
//   1. Create a Firebase project at https://console.firebase.google.com
//   2. Add a Web App to it; Firebase shows you a `firebaseConfig` object.
//   3. Enable Realtime Database (NOT Firestore) in the console.
//   4. Paste the values below and set the security rules from
//      firebase-rules.json (repo root).
//
// This config is PUBLIC by design — Firebase web config is meant to ship in
// client code and is not a secret (unlike the ESPN cookies, which stay in a
// gitignored .env). It's safe to commit. Access is controlled by the
// database security rules, not by hiding these values.
//
// Until the databaseURL below is filled in (it still contains "PASTE"), the
// board runs WITHOUT sync: it shows a "NOT SYNCED" status and drafted picks
// are in-memory only (lost on refresh, not shared across devices).

export const firebaseConfig = {
  apiKey: "PASTE_API_KEY",
  authDomain: "PASTE_PROJECT.firebaseapp.com",
  databaseURL: "https://PASTE_PROJECT-default-rtdb.firebaseio.com",
  projectId: "PASTE_PROJECT",
  appId: "PASTE_APP_ID",
};
