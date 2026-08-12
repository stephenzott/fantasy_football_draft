// Firebase web config for draft-day sync.
//
// This config is PUBLIC by design — Firebase web config is meant to ship in
// client code and is not a secret (unlike the ESPN cookies, which stay in a
// gitignored .env). It's safe to commit. Access is controlled by the database
// security rules (firebase-rules.json), not by hiding these values.
//
// NOTE: this file only EXPORTS the config object. app.js imports it and does
// initializeApp()/getDatabase() itself (via the lazily-loaded SDK), so this
// file must NOT import the SDK or call initializeApp — the console's copy-paste
// snippet includes those lines, but they'd break this ES module (bare
// "firebase/app" specifier won't resolve in the browser without a bundler).

export const firebaseConfig = {
  apiKey: "AIzaSyCg4J920Na5ADzo25pfMyURsEcYzM1XFp8",
  authDomain: "gen-lang-client-0026826837.firebaseapp.com",
  databaseURL: "https://gen-lang-client-0026826837-default-rtdb.firebaseio.com",
  projectId: "gen-lang-client-0026826837",
  storageBucket: "gen-lang-client-0026826837.firebasestorage.app",
  messagingSenderId: "814240070558",
  appId: "1:814240070558:web:0dcee2cd02f7b6ce4b748f",
};
