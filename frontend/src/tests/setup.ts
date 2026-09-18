import '@testing-library/jest-dom/vitest';

// Polyfill scrollIntoView in jsdom environment
window.HTMLElement.prototype.scrollIntoView = function () {};
