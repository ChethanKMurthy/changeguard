export function loadPrefs(storage) {
  const raw = storage.getItem("prefs");
  return raw ? JSON.parse(raw) : {};
}
