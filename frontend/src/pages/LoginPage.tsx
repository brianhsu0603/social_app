import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { auth as authApi } from "@/api/endpoints";
import { useAuth } from "@/store/auth";

export default function LoginPage() {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const setAuth = useAuth((s) => s.setAuth);
  const navigate = useNavigate();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const { access_token } = await authApi.login(identifier, password);
      localStorage.setItem("token", access_token);
      const me = await authApi.me();
      setAuth(access_token, me);
      navigate("/");
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "login failed");
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-16 p-6 bg-white rounded shadow">
      <h1 className="text-xl font-bold mb-4">Sign in</h1>
      <form onSubmit={onSubmit} className="space-y-3">
        <input
          className="w-full border rounded px-3 py-2"
          placeholder="email or username"
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
        />
        <input
          className="w-full border rounded px-3 py-2"
          type="password"
          placeholder="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className="w-full bg-blue-600 text-white rounded py-2 hover:bg-blue-700">
          Sign in
        </button>
      </form>
      <p className="text-sm mt-4">
        No account? <Link to="/register" className="text-blue-600">Register</Link>
      </p>
    </div>
  );
}
