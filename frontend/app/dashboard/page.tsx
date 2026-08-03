"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/utils/supabase/client";
import { BrainCircuit, LogOut, Upload, FileText, Loader2, ArrowRight, BookOpen, AlertCircle, CheckCircle2, BarChart, Target } from "lucide-react";
import Link from "next/link";
import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

interface PDFInfo {
  filename: string;
  page_count: number;
  estimated_tokens: number;
  max_questions_allowed: number;
  allowed_question_counts: number[];
}

interface QuizItem {
  id: string;
  filename: string;
  total_questions: number;
  created_at: string;
  llm_model: string;
}

export default function Dashboard() {
  const [user, setUser] = useState<any>(null);
  const [sessionToken, setSessionToken] = useState<string>("");
  const [loading, setLoading] = useState(true);
  
  // Upload & Config state
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState("");
  const [pdfInfo, setPdfInfo] = useState<PDFInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // Form State
  const [startPage, setStartPage] = useState<number>(1);
  const [endPage, setEndPage] = useState<number>(1);
  const [questionCount, setQuestionCount] = useState<number>(10);
  
  // History State
  const [quizzes, setQuizzes] = useState<QuizItem[]>([]);
  const [fetchingHistory, setFetchingHistory] = useState(false);
  const [analytics, setAnalytics] = useState<{ total_quizzes: number, total_questions: number } | null>(null);
  
  const router = useRouter();

  useEffect(() => {
    const checkUser = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        router.push("/");
      } else {
        setUser(session.user);
        setSessionToken(session.access_token);
        fetchQuizzes(session.access_token);
        fetchAnalytics(session.access_token);
      }
      setLoading(false);
    };
    checkUser();
  }, [router]);

  const fetchAnalytics = async (token: string) => {
    try {
      const res = await axios.get(`${API_BASE}/analytics`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setAnalytics(res.data);
    } catch (err) {
      console.error("Failed to fetch analytics", err);
    }
  };

  const fetchQuizzes = async (token: string) => {
    setFetchingHistory(true);
    try {
      const res = await axios.get(`${API_BASE}/quizzes`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setQuizzes(res.data.quizzes || []);
    } catch (err) {
      console.error("Failed to fetch quizzes", err);
    } finally {
      setFetchingHistory(false);
    }
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/");
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (selectedFile.type !== "application/pdf") {
        setError("Invalid file type. Please upload a PDF.");
        return;
      }
      setFile(selectedFile);
      
      // Auto-upload to get PDF info
      await fetchPdfInfo(selectedFile);
    }
  };

  const fetchPdfInfo = async (selectedFile: File) => {
    setUploading(true);
    setLoadingMessage("Uploading PDF...");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      setLoadingMessage("Parsing PDF...");
      const res = await axios.post(`${API_BASE}/pdf-info`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
          Authorization: `Bearer ${sessionToken}`
        }
      });
      
      const info: PDFInfo = res.data;
      setPdfInfo(info);
      setStartPage(1);
      setEndPage(info.page_count);
      
      // Select the first valid question count or fallback to 10
      const defaultQ = info.allowed_question_counts?.includes(10) ? 10 : (info.allowed_question_counts?.[0] || 10);
      setQuestionCount(defaultQ);
      
    } catch (err: any) {
      if (err.response?.status === 401) {
        setError("Authentication expired. Please log in again.");
      } else if (err.response?.data?.detail) {
        setError(err.response.data.detail);
      } else {
        setError("Network error. Could not upload PDF.");
      }
      setFile(null);
    } finally {
      setUploading(false);
      setLoadingMessage("");
    }
  };

  const handleGenerate = async () => {
    if (!file || !pdfInfo) return;
    
    // Validation
    if (startPage < 1) {
      setError("Start page must be at least 1");
      return;
    }
    if (endPage > pdfInfo.page_count) {
      setError(`End page cannot exceed total pages (${pdfInfo.page_count})`);
      return;
    }
    if (startPage > endPage) {
      setError("Start page cannot be greater than end page");
      return;
    }

    setError(null);
    setUploading(true);
    setLoadingMessage("Preparing Questions...");

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("total_questions", questionCount.toString());
      formData.append("start_page", startPage.toString());
      formData.append("end_page", endPage.toString());

      setTimeout(() => { setLoadingMessage("Almost Ready..."); }, 3000);

      const res = await axios.post(`${API_BASE}/generate-quiz`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
          Authorization: `Bearer ${sessionToken}`
        }
      });

      // Redirect to quiz interface
      router.push(`/quiz/${res.data.id}`);

    } catch (err: any) {
      if (err.response?.status === 422) {
        setError("Invalid configuration. Please check your page range and question counts.");
      } else if (err.response?.data?.detail) {
        setError(err.response.data.detail);
      } else {
        setError("Quiz generation failed. Please try again.");
      }
      setUploading(false);
    }
  };

  const resetUpload = () => {
    setFile(null);
    setPdfInfo(null);
    setError(null);
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 dark:bg-slate-950">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-50">
      
      {/* Navbar */}
      <header className="sticky top-0 z-50 w-full border-b border-slate-200/50 dark:border-slate-800/50 bg-white/50 dark:bg-slate-950/50 backdrop-blur-xl">
        <div className="container mx-auto flex h-16 items-center justify-between px-4 md:px-6">
          <Link href="/dashboard" className="flex items-center gap-2 font-bold text-xl tracking-tight">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
              <BrainCircuit className="h-5 w-5" />
            </div>
            Make My Quiz
          </Link>
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium hidden sm:inline-block text-slate-600 dark:text-slate-400">
              {user?.email}
            </span>
            <button
              onClick={handleLogout}
              className="inline-flex h-9 items-center justify-center rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              <LogOut className="mr-2 h-4 w-4" />
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 container mx-auto px-4 py-8 md:px-6 max-w-5xl">
        <div className="flex flex-col gap-12">
          
          {/* Top/Middle Section: Upload or Config */}
          <section className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
              <div>
                <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
                <p className="text-slate-500 dark:text-slate-400 mt-1">Upload a new PDF to generate an interactive quiz.</p>
              </div>
              
              {analytics && (
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-3 shadow-sm">
                    <div className="bg-indigo-50 dark:bg-indigo-900/30 p-2 rounded-lg text-indigo-600 dark:text-indigo-400">
                      <BarChart className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Total Quizzes</p>
                      <p className="text-lg font-bold leading-none mt-1">{analytics.total_quizzes}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-3 shadow-sm">
                    <div className="bg-green-50 dark:bg-green-900/30 p-2 rounded-lg text-green-600 dark:text-green-400">
                      <Target className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Questions Answered</p>
                      <p className="text-lg font-bold leading-none mt-1">{analytics.total_questions}</p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800 flex items-start gap-3 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-200">
                <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
                <p className="text-sm font-medium">{error}</p>
              </div>
            )}

            {!pdfInfo ? (
              /* Upload Zone */
              <div className="rounded-2xl border border-slate-200 bg-white p-12 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <div className="flex flex-col items-center justify-center text-center max-w-md mx-auto">
                  <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-indigo-50 dark:bg-indigo-900/20">
                    {uploading ? (
                      <Loader2 className="h-10 w-10 text-indigo-600 animate-spin dark:text-indigo-400" />
                    ) : (
                      <Upload className="h-10 w-10 text-indigo-600 dark:text-indigo-400" />
                    )}
                  </div>
                  
                  {uploading ? (
                    <div className="space-y-2">
                      <h3 className="text-xl font-semibold">{loadingMessage}</h3>
                      <p className="text-sm text-slate-500 dark:text-slate-400">This may take a moment.</p>
                    </div>
                  ) : (
                    <>
                      <h3 className="mb-2 text-xl font-bold">Upload Study Material</h3>
                      <p className="mb-8 text-sm text-slate-500 dark:text-slate-400">
                        Select a PDF file to extract concepts and generate a quiz.
                      </p>
                      
                      <label 
                        htmlFor="pdf-upload" 
                        className="flex w-full cursor-pointer items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-6 py-10 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:hover:bg-slate-800 transition-colors"
                      >
                        <div className="flex flex-col items-center space-y-3">
                          <FileText className="h-10 w-10 text-slate-400" />
                          <span className="text-base font-medium text-indigo-600 dark:text-indigo-400">
                            Click to browse files
                          </span>
                          <span className="text-xs text-slate-500">PDF up to 10MB</span>
                        </div>
                        <input 
                          id="pdf-upload" 
                          type="file" 
                          accept="application/pdf" 
                          className="hidden" 
                          onChange={handleFileChange}
                          disabled={uploading}
                        />
                      </label>
                    </>
                  )}
                </div>
              </div>
            ) : (
              /* Configuration Panel */
              <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6 mb-8 border-b border-slate-100 pb-8 dark:border-slate-800">
                  <div className="flex items-start gap-4">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400">
                      <CheckCircle2 className="h-6 w-6" />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold">{pdfInfo.filename}</h3>
                      <p className="text-sm text-slate-500 dark:text-slate-400">
                        {pdfInfo.page_count} {pdfInfo.page_count === 1 ? 'page' : 'pages'} successfully parsed
                      </p>
                    </div>
                  </div>
                  <button 
                    onClick={resetUpload}
                    disabled={uploading}
                    className="text-sm font-medium text-slate-500 hover:text-slate-900 dark:hover:text-slate-200 transition-colors"
                  >
                    Upload different file
                  </button>
                </div>

                <div className="grid gap-8 md:grid-cols-2 max-w-3xl">
                  {/* Page Range Config */}
                  <div className="space-y-4">
                    <div>
                      <h4 className="font-semibold mb-1">Page Range</h4>
                      <p className="text-sm text-slate-500 dark:text-slate-400">Which pages do you want to test on?</p>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="space-y-1.5 flex-1">
                        <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Start Page</label>
                        <input 
                          type="number" 
                          min={1} 
                          max={pdfInfo.page_count}
                          value={startPage}
                          onChange={(e) => setStartPage(Number(e.target.value))}
                          disabled={uploading}
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50 disabled:opacity-50"
                        />
                      </div>
                      <span className="text-slate-400 pt-5">—</span>
                      <div className="space-y-1.5 flex-1">
                        <label className="text-xs font-medium text-slate-700 dark:text-slate-300">End Page</label>
                        <input 
                          type="number" 
                          min={1} 
                          max={pdfInfo.page_count}
                          value={endPage}
                          onChange={(e) => setEndPage(Number(e.target.value))}
                          disabled={uploading}
                          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50 disabled:opacity-50"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Question Count Config */}
                  <div className="space-y-4">
                    <div>
                      <h4 className="font-semibold mb-1">Number of Questions</h4>
                      <p className="text-sm text-slate-500 dark:text-slate-400">How many questions to generate?</p>
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Amount</label>
                        <span className="text-[10px] text-slate-500">Max: {pdfInfo.max_questions_allowed}</span>
                      </div>
                      <input
                        type="number"
                        min={1}
                        max={pdfInfo.max_questions_allowed}
                        value={questionCount}
                        onChange={(e) => setQuestionCount(Number(e.target.value))}
                        disabled={uploading}
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50 disabled:opacity-50"
                      />
                      <div className="flex flex-wrap gap-2 pt-2">
                        {[5, 10, 15, 20, 30].map((num) => (
                          <button
                            key={num}
                            type="button"
                            disabled={uploading || num > pdfInfo.max_questions_allowed}
                            onClick={() => setQuestionCount(num)}
                            className={`px-2 py-1 text-xs font-medium rounded-md border ${
                              questionCount === num
                                ? "bg-indigo-50 border-indigo-200 text-indigo-700 dark:bg-indigo-900/30 dark:border-indigo-800 dark:text-indigo-300"
                                : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50 dark:bg-slate-900 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
                            } disabled:opacity-50 disabled:pointer-events-none transition-colors`}
                          >
                            {num}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-10 pt-6 border-t border-slate-100 dark:border-slate-800 flex justify-end">
                  <button
                    onClick={handleGenerate}
                    disabled={uploading}
                    className="inline-flex h-12 w-full md:w-auto items-center justify-center rounded-xl bg-indigo-600 px-8 text-base font-semibold text-white shadow-sm transition-all hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 disabled:pointer-events-none disabled:opacity-70"
                  >
                    {uploading ? (
                      <>
                        <Loader2 className="mr-3 h-5 w-5 animate-spin" />
                        {loadingMessage || "Processing..."}
                      </>
                    ) : (
                      <>
                        Generate Quiz <ArrowRight className="ml-2 h-5 w-5" />
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* Bottom Section: Recent Quizzes */}
          <section className="space-y-6 pt-6">
            <h2 className="text-2xl font-bold tracking-tight">Recent Quizzes</h2>
            
            {fetchingHistory ? (
              <div className="flex h-32 items-center justify-center rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900/50">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
              </div>
            ) : quizzes.length === 0 ? (
              <div className="flex h-40 flex-col items-center justify-center rounded-xl border border-slate-200 border-dashed bg-slate-50 dark:border-slate-800 dark:bg-slate-900/20">
                <BookOpen className="mb-3 h-8 w-8 text-slate-400" />
                <p className="text-sm font-medium text-slate-600 dark:text-slate-300">No quizzes found</p>
                <p className="text-xs text-slate-500 mt-1">Quizzes you generate will appear here.</p>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {quizzes.map((quiz) => (
                  <Link 
                    key={quiz.id} 
                    href={`/quiz/${quiz.id}`}
                    className="group flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:border-indigo-300 hover:shadow-md dark:border-slate-800 dark:bg-slate-900 dark:hover:border-indigo-800"
                  >
                    <div className="mb-4">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-400">
                          <BookOpen className="h-5 w-5" />
                        </div>
                        <span className="inline-flex items-center rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-medium text-green-700 ring-1 ring-inset ring-green-600/20 dark:bg-green-900/30 dark:text-green-400 dark:ring-green-800">
                          Completed
                        </span>
                      </div>
                      <h4 className="font-semibold text-slate-900 dark:text-slate-100 line-clamp-1 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                        {quiz.filename}
                      </h4>
                    </div>
                    <div className="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400 pt-4 border-t border-slate-100 dark:border-slate-800">
                      <span>{new Date(quiz.created_at).toLocaleDateString()}</span>
                      <span className="font-medium text-slate-700 dark:text-slate-300">{quiz.total_questions} Questions</span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>

        </div>
      </main>
    </div>
  );
}
