"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, type PriceBar, type NewsArticle } from "@/lib/api";

export default function StockDetailPage() {
  const params = useParams();
  const symbol = (params.symbol as string)?.toUpperCase();

  const [prices, setPrices] = useState<PriceBar[]>([]);
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    Promise.all([
      api.stocks.prices(symbol, "1Day", 90).catch(() => []),
      api.stocks.news(symbol, 20).catch(() => []),
    ]).then(([p, n]) => {
      setPrices(p);
      setNews(n);
      setLoading(false);
    });
  }, [symbol]);

  if (!symbol) return null;

  const latestPrice = prices.length > 0 ? prices[prices.length - 1] : null;
  const prevPrice = prices.length > 1 ? prices[prices.length - 2] : null;
  const change =
    latestPrice && prevPrice
      ? ((latestPrice.close - prevPrice.close) / prevPrice.close) * 100
      : null;

  // Simple sparkline using CSS bars
  const priceMin = prices.length > 0 ? Math.min(...prices.map((p) => p.low)) : 0;
  const priceMax = prices.length > 0 ? Math.max(...prices.map((p) => p.high)) : 1;
  const priceRange = priceMax - priceMin || 1;

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4">
        <Link href="/" className="text-muted-foreground hover:text-foreground">
          &larr; Dashboard
        </Link>
      </div>

      <div className="flex items-baseline gap-4">
        <h2 className="text-3xl font-bold tracking-tight">{symbol}</h2>
        {latestPrice && (
          <>
            <span className="text-2xl font-mono">
              ${latestPrice.close.toFixed(2)}
            </span>
            {change !== null && (
              <span
                className={`text-lg font-mono ${
                  change >= 0 ? "text-green-500" : "text-red-500"
                }`}
              >
                {change >= 0 ? "+" : ""}
                {change.toFixed(2)}%
              </span>
            )}
          </>
        )}
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : (
        <>
          {/* Price chart (simple bar visualization) */}
          <Card>
            <CardHeader>
              <CardTitle>Price History (90 days)</CardTitle>
              <CardDescription>
                {prices.length} daily bars loaded
              </CardDescription>
            </CardHeader>
            <CardContent>
              {prices.length > 0 ? (
                <div className="flex items-end gap-px h-48">
                  {prices.map((p, i) => {
                    const height =
                      ((p.close - priceMin) / priceRange) * 100;
                    const isUp = p.close >= p.open;
                    return (
                      <div
                        key={i}
                        className={`flex-1 min-w-[2px] rounded-t-sm ${
                          isUp ? "bg-green-500" : "bg-red-500"
                        }`}
                        style={{ height: `${Math.max(height, 2)}%` }}
                        title={`${new Date(p.timestamp).toLocaleDateString()}: $${p.close.toFixed(2)}`}
                      />
                    );
                  })}
                </div>
              ) : (
                <div className="flex h-48 items-center justify-center rounded-md border border-dashed">
                  <p className="text-sm text-muted-foreground">
                    No price data yet. Run the backfill or wait for collection.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Key stats */}
          {latestPrice && (
            <div className="grid gap-4 md:grid-cols-5">
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Open</CardDescription>
                  <CardTitle className="text-xl font-mono">
                    ${latestPrice.open.toFixed(2)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>High</CardDescription>
                  <CardTitle className="text-xl font-mono">
                    ${latestPrice.high.toFixed(2)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Low</CardDescription>
                  <CardTitle className="text-xl font-mono">
                    ${latestPrice.low.toFixed(2)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Close</CardDescription>
                  <CardTitle className="text-xl font-mono">
                    ${latestPrice.close.toFixed(2)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Volume</CardDescription>
                  <CardTitle className="text-xl font-mono">
                    {(latestPrice.volume / 1_000_000).toFixed(1)}M
                  </CardTitle>
                </CardHeader>
              </Card>
            </div>
          )}

          {/* News feed */}
          <Card>
            <CardHeader>
              <CardTitle>Recent News</CardTitle>
              <CardDescription>
                {news.length > 0
                  ? `${news.length} articles`
                  : "No news articles collected yet"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {news.length > 0 ? (
                <div className="space-y-4">
                  {news.map((article) => (
                    <div
                      key={article.id}
                      className="flex items-start justify-between gap-4 border-b pb-4 last:border-0 last:pb-0"
                    >
                      <div className="flex-1 space-y-1">
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-medium hover:underline"
                        >
                          {article.headline}
                        </a>
                        {article.summary && (
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {article.summary}
                          </p>
                        )}
                        <p className="text-xs text-muted-foreground">
                          {article.source} &middot;{" "}
                          {new Date(article.published_at).toLocaleDateString()}
                        </p>
                      </div>
                      {article.sentiment_score !== null && (
                        <span
                          className={`shrink-0 rounded-full px-2 py-1 text-xs font-medium ${
                            article.sentiment_score > 0.2
                              ? "bg-green-500/10 text-green-500"
                              : article.sentiment_score < -0.2
                              ? "bg-red-500/10 text-red-500"
                              : "bg-yellow-500/10 text-yellow-500"
                          }`}
                        >
                          {article.sentiment_score.toFixed(2)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex h-32 items-center justify-center rounded-md border border-dashed">
                  <p className="text-sm text-muted-foreground">
                    News will appear once the Finnhub collector runs
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
