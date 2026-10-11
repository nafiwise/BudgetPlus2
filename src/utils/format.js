export const money = value => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
export const round = value => Math.round((value + Number.EPSILON) * 100) / 100;
export const sum = (items, field = 'amount') => round(items.reduce((total, item) => total + item[field], 0));
export const daysBetween = (start, end) => Math.round((Date.parse(end) - Date.parse(start)) / 86400000);
