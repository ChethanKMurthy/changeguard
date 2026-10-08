export function renderBanner(el: HTMLElement, message: string): void {
  el.innerHTML = `<strong>${message}</strong>`;
}
