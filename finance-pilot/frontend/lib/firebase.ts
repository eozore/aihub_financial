// lib/firebase.ts - Configuração oficial do Firebase
import { initializeApp, getApps, getApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseApiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
const firebaseAuthDomain = process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN;
const firebaseProjectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
const firebaseStorageBucket = process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || "";
const firebaseMessagingSenderId =
  process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || "";
const firebaseAppId = process.env.NEXT_PUBLIC_FIREBASE_APP_ID || "";

const missingRequiredEnvVar = [
  ["NEXT_PUBLIC_FIREBASE_API_KEY", firebaseApiKey],
  ["NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN", firebaseAuthDomain],
  ["NEXT_PUBLIC_FIREBASE_PROJECT_ID", firebaseProjectId],
].find(([, value]) => !value);

if (missingRequiredEnvVar) {
  throw new Error(
    `Missing required environment variable: ${missingRequiredEnvVar[0]}. ` +
    "Check your .env.local or build configuration."
  );
}

const firebaseConfig = {
  apiKey: firebaseApiKey,
  authDomain: firebaseAuthDomain,
  projectId: firebaseProjectId,
  storageBucket: firebaseStorageBucket,
  messagingSenderId: firebaseMessagingSenderId,
  appId: firebaseAppId,
};

// Initialize Firebase (Singleton pattern)
const app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
export const auth = getAuth(app);
