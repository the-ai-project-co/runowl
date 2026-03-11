import { writable } from 'svelte/store';
import { browser } from '$app/environment';

const initial = browser ? (localStorage.getItem('theme') ?? 'dark') : 'dark';

export const theme = writable<'dark' | 'light'>(initial as 'dark' | 'light');

theme.subscribe((value) => {
	if (browser) {
		localStorage.setItem('theme', value);
		document.documentElement.setAttribute('data-theme', value);
	}
});

export function toggleTheme() {
	theme.update((t) => (t === 'dark' ? 'light' : 'dark'));
}
