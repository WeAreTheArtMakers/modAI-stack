/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#101727",
        cloud: "#f4f6f9",
        cyan: "#2f9fb5",
        coral: "#de775f",
      },
      boxShadow: {
        panel: "0 18px 50px rgba(16, 23, 39, 0.08)",
      },
    },
  },
  plugins: [],
};
