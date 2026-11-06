/** ACE Bridge service worker (skeleton). Native-messaging connection and tab skills arrive in S24 (§11). */
import { BRIDGE_PROTOCOL_VERSION } from "./protocol";

chrome.runtime.onInstalled.addListener(() => {
  console.info(`ACE Bridge installed (protocol v${BRIDGE_PROTOCOL_VERSION}).`);
});
