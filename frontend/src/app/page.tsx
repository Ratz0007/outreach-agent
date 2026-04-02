import React from 'react';
import Link from 'next/link';
import { 
  Briefcase, 
  Zap, 
  Target, 
  MessageSquare, 
  Sparkles, 
  ArrowRight,
  Code,
  Globe
} from 'lucide-react';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-indigo-100 dark:selection:bg-indigo-900/30">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 w-full border-b bg-background/80 backdrop-blur-md">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold">
              OA
            </div>
            <span className="font-bold text-xl tracking-tight">Outreach Agent</span>
          </div>
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-muted-foreground">
            <Link href="#features" className="hover:text-primary transition-colors">Features</Link>
            <Link href="#how-it-works" className="hover:text-primary transition-colors">How it Works</Link>
            <Link href="https://github.com/ratinsharma" target="_blank" className="hover:text-primary transition-colors flex items-center gap-1">
              <Code className="w-4 h-4" /> GitHub
            </Link>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/login" className="text-sm font-medium hover:text-primary transition-colors">Log In</Link>
            <Link href="/register" className="bg-primary text-primary-foreground px-4 py-2 rounded-full text-sm font-semibold hover:opacity-90 transition-all shadow-lg shadow-primary/20">
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative overflow-hidden pt-20 pb-32 lg:pt-32 lg:pb-48">
        <div className="container mx-auto px-4 relative z-10">
          <div className="max-w-4xl mx-auto text-center">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 text-xs font-bold uppercase tracking-wider mb-6 animate-in fade-in slide-in-from-bottom-3 duration-1000">
              <Sparkles className="w-3 h-3" /> Powered by Agentic AI
            </div>
            <h1 className="text-5xl lg:text-7xl font-extrabold tracking-tight mb-8 bg-clip-text text-transparent bg-gradient-to-b from-foreground to-foreground/70 animate-in fade-in slide-in-from-bottom-4 duration-1200">
              Your Personal <span className="bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text">24/7 Career Agent</span>
            </h1>
            <p className="text-xl text-muted-foreground mb-10 max-w-2xl mx-auto leading-relaxed animate-in fade-in slide-in-from-bottom-5 duration-1400">
              Automate the grunt work of your job search. Source high-fit roles, enrich contacts, and send personalized outreach—all managed by our smart voice-controlled agent.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 animate-in fade-in slide-in-from-bottom-6 duration-1600">
              <Link href="/register" className="w-full sm:w-auto bg-primary text-primary-foreground px-8 py-4 rounded-2xl text-lg font-bold hover:scale-[1.02] transition-all shadow-xl shadow-primary/25 flex items-center justify-center gap-2 group">
                Start for Free <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Link>
              <button className="w-full sm:w-auto px-8 py-4 rounded-2xl text-lg font-bold border hover:bg-muted/50 transition-all">
                See it in Action
              </button>
            </div>
          </div>
        </div>

        {/* Backdrop Glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-full -z-10 pointer-events-none overflow-hidden">
          <div className="absolute top-[-10%] left-[20%] w-[40%] h-[60%] rounded-full bg-indigo-200/50 dark:bg-indigo-900/10 blur-[120px]" />
          <div className="absolute bottom-[10%] right-[20%] w-[35%] h-[50%] rounded-full bg-purple-200/50 dark:bg-purple-900/10 blur-[120px]" />
        </div>
      </section>

      {/* Features Grid */}
      <section id="features" className="py-24 bg-muted/30">
        <div className="container mx-auto px-4">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <h2 className="text-3xl font-bold mb-4">Dictate. Automate. Land the Job.</h2>
            <p className="text-muted-foreground">Everything you need to automate 100% of the repetitive tasks in your job hunt.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {/* Feature 1 */}
            <div className="group p-8 rounded-3xl bg-background border hover:border-indigo-500/50 transition-all hover:shadow-2xl hover:shadow-indigo-500/10 h-full">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-900/20 flex items-center justify-center text-indigo-600 mb-6 group-hover:scale-110 transition-transform">
                <Target className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold mb-3">AI Deep Sourcing</h3>
              <p className="text-muted-foreground text-sm leading-relaxed">
                Connects to Adzuna and LinkedIn to find roles that perfectly match your desired stack and seniority.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="group p-8 rounded-3xl bg-background border hover:border-purple-500/50 transition-all hover:shadow-2xl hover:shadow-purple-500/10 h-full">
              <div className="w-12 h-12 rounded-2xl bg-purple-50 dark:bg-purple-900/20 flex items-center justify-center text-purple-600 mb-6 group-hover:scale-110 transition-transform">
                <MessageSquare className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold mb-3">Agentic Outreach</h3>
              <p className="text-muted-foreground text-sm leading-relaxed">
                Generates personalized emails and LinkedIn messages using Claude 3.5. Approves and sends drafts automatically.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="group p-8 rounded-3xl bg-background border hover:border-emerald-500/50 transition-all hover:shadow-2xl hover:shadow-emerald-500/10 h-full">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 dark:bg-emerald-900/20 flex items-center justify-center text-emerald-600 mb-6 group-hover:scale-110 transition-transform">
                <Zap className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold mb-3">Voice Command</h3>
              <p className="text-muted-foreground text-sm leading-relaxed">
                Simply say "Source 10 jobs in London" and your agent will handle the rest. Hands-free job seeking.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Trust & Details Section */}
      <section className="py-24 border-t">
        <div className="container mx-auto px-4">
          <div className="flex flex-col lg:flex-row items-center gap-16">
            <div className="lg:w-1/2 space-y-8">
              <h2 className="text-4xl font-bold leading-tight">
                Designed for the <span className="bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent underline decoration-indigo-200 underline-offset-8">Modern Job Seeker</span>
              </h2>
              <div className="space-y-4">
                {[
                  "Built-in A/B testing for outreach variants",
                  "Automated contact enrichment via Hunter & Apollo",
                  "Real-time LinkedIn quota management",
                  "One-click PDF CV tailoring per role"
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center">
                      <Zap className="w-3 h-3 text-white fill-white" />
                    </div>
                    <span className="font-medium">{item}</span>
                  </div>
                ))}
              </div>
              <div className="p-6 rounded-3xl bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-100 dark:border-indigo-800">
                <p className="text-sm font-medium italic text-indigo-700 dark:text-indigo-300">
                   "This agent saved me 20 hours a week in manually tracking spreadsheet items. The voice coach is a game changer."
                </p>
                <div className="mt-4 flex items-center gap-3">
                   <div className="w-8 h-8 rounded-full bg-slate-200" />
                   <div>
                     <p className="text-xs font-bold">Ratin S.</p>
                     <p className="text-[10px] text-muted-foreground">Founder, Outreach Agent</p>
                   </div>
                </div>
              </div>
            </div>
            <div className="lg:w-1/2 relative">
              <div className="aspect-[4/3] rounded-3xl bg-gradient-to-br from-indigo-100 to-purple-100 dark:from-indigo-950/40 dark:to-purple-950/40 overflow-hidden shadow-2xl border">
                {/* Visual placeholder for app UI */}
                <div className="p-4 h-full flex flex-col gap-4">
                  <div className="h-12 w-full bg-background rounded-xl border flex items-center px-4 justify-between">
                    <div className="flex items-center gap-2">
                       <div className="w-3 h-3 rounded-full bg-red-400" />
                       <div className="w-3 h-3 rounded-full bg-amber-400" />
                       <div className="w-3 h-3 rounded-full bg-emerald-400" />
                    </div>
                    <div className="w-32 h-3 bg-muted rounded-full" />
                  </div>
                  <div className="flex gap-4 h-full">
                    <div className="w-1/3 bg-background/50 rounded-xl border border-dashed flex flex-col gap-2 p-3">
                       <div className="h-4 w-full bg-muted rounded-md" />
                       <div className="h-4 w-2/3 bg-muted rounded-md" />
                    </div>
                    <div className="flex-1 bg-background rounded-xl border shadow-sm p-4 flex flex-col gap-4">
                       <div className="flex justify-between items-center">
                         <div className="h-6 w-24 bg-muted rounded-md" />
                         <div className="h-6 w-12 bg-indigo-100 rounded-md" />
                       </div>
                       <div className="h-2 w-full bg-muted rounded-full" />
                       <div className="h-2 w-full bg-muted rounded-full" />
                       <div className="h-2 w-3/4 bg-muted rounded-full" />
                       <div className="mt-auto h-10 w-full bg-indigo-500 rounded-xl" />
                    </div>
                  </div>
                </div>
              </div>
              <div className="absolute -bottom-8 -left-8 p-6 rounded-2xl bg-background border shadow-2xl animate-bounce">
                <div className="flex items-center gap-3">
                   <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center text-emerald-600">
                     <Target className="w-5 h-5" />
                   </div>
                   <div>
                     <p className="text-xs text-muted-foreground uppercase font-bold tracking-tighter">New Job Sourced</p>
                     <p className="text-sm font-bold">Product Designer @ Stripe</p>
                   </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t bg-muted/20">
        <div className="container mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-primary flex items-center justify-center text-[10px] text-white">OA</div>
            <span className="font-bold">Outreach Agent</span>
          </div>
          <div className="flex gap-8 text-sm text-muted-foreground">
            <Link href="#" className="hover:text-primary underline decoration-muted-foreground/30 underline-offset-4">Privacy</Link>
            <Link href="#" className="hover:text-primary underline decoration-muted-foreground/30 underline-offset-4">Terms</Link>
            <Link href="mailto:hello@outreach.app" className="hover:text-primary underline decoration-muted-foreground/30 underline-offset-4">Contact</Link>
          </div>
          <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} Outreach Agent. Built for job seekers.</p>
        </div>
      </footer>
    </div>
  );
}
