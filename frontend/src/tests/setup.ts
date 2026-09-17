import '@testing-library/jest-dom';

// Polyfill scrollIntoView in jsdom environment
window.HTMLElement.prototype.scrollIntoView = function () {};
