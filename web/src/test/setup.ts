import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock clipboard API
const clipboardMock = {
  writeText: vi.fn().mockResolvedValue(undefined),
  readText: vi.fn().mockResolvedValue(''),
};
Object.defineProperty(navigator, 'clipboard', {
  value: clipboardMock,
  writable: true,
  configurable: true,
});

// Export for use in tests
export { clipboardMock };
