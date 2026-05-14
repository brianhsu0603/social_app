import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { auth as authApi } from "@/api/endpoints";
import { useAuth } from "@/store/auth";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const setAuth = useAuth((s) => s.setAuth);
  const navigate = useNavigate();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const { access_token } = await authApi.register({
        email,
        username,
        display_name: displayName,
        password,
      });
      localStorage.setItem("token", access_token);
      const me = await authApi.me();
      setAuth(access_token, me);
      navigate("/");
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "registration failed");
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-16 p-6 bg-white rounded shadow">
      <h1 className="text-xl font-bold mb-4">Create account</h1>
      <form onSubmit={onSubmit} className="space-y-3">
        <input className="w-full border rounded px-3 py-2" placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className="w-full border rounded px-3 py-2" placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input className="w-full border rounded px-3 py-2" placeholder="display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        <input className="w-full border rounded px-3 py-2" type="password" placeholder="password (min 8)" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className="w-full bg-blue-600 text-white rounded py-2 hover:bg-blue-700">
          Register
        </button>
      </form>
      <p className="text-sm mt-4">
        Have an account? <Link to="/login" className="text-blue-600">Sign in</Link>
      </p>
    </div>
  );
}
