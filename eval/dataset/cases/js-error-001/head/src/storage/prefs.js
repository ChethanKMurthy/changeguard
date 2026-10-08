export function loadPrefs(storage) {
  try {
    const raw = storage.getItem("prefs");
    return raw ? JSON.parse(raw) : {};
  } catch (err) {}
  return {};
}
