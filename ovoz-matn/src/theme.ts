export const colors = {
  bg: '#0F1420',
  surface: '#171E2E',
  surface2: '#202A3F',
  border: '#2B3650',
  text: '#EEF2FA',
  textDim: '#9AA6BF',
  textFaint: '#66728C',
  accent: '#3D8BFF',
  rec: '#FF4D5E',
  ok: '#2FBF71',
  warn: '#F5B83D',
  lang: {
    uz: '#2FBF71',
    ru: '#3D8BFF',
    en: '#F5B83D',
  } as Record<string, string>,
};

export const langColor = (lang?: string) => (lang && colors.lang[lang]) || colors.textFaint;
