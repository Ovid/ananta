import { useState, useEffect } from 'react'

export function useTheme() {
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('shesha-theme')
    return saved ? saved === 'dark' : true // Default dark
  })

  useEffect(() => {
    localStorage.setItem('shesha-theme', dark ? 'dark' : 'light')
    document.documentElement.classList.toggle('light', !dark)
  }, [dark])

  return { dark, toggle: () => setDark(d => !d) }
}
