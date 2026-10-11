import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { number } from "../lib/format";
const months = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];
export function MonthlyChart({ values }: { values: number[] }) {
  const data = values.map((kwh, index) => ({ month: months[index], kwh }));
  return (
    <>
      <div
        className="monthly-chart"
        role="img"
        aria-label={`Monthly energy in kilowatt hours: ${data.map((row) => `${row.month} ${number(row.kwh)}`).join(", ")}`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 12, right: 5, left: -18, bottom: 0 }}
          >
            <CartesianGrid
              vertical={false}
              stroke="#e8e9e0"
              strokeDasharray="3 5"
            />
            <XAxis
              dataKey="month"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#7b8178", fontSize: 11 }}
              interval={0}
            />
            <YAxis
              tickFormatter={(value) => `${number(value / 1000, 1)}k`}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#7b8178", fontSize: 11 }}
            />
            <Tooltip
              cursor={{ fill: "#f2f3e9" }}
              contentStyle={{
                borderRadius: 10,
                borderColor: "#e1e4d7",
                fontSize: 12,
              }}
              formatter={(value) => [`${number(Number(value))} kWh`, "Energy"]}
            />
            <Bar
              dataKey="kwh"
              fill="#c4d798"
              radius={[4, 4, 0, 0]}
              activeBar={{ fill: "#1c4b38" }}
              maxBarSize={34}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="chart-table">
        <summary>View monthly values</summary>
        <div className="month-values">
          {data.map((row) => (
            <div key={row.month}>
              <span>{row.month}</span>
              <strong>{number(row.kwh)} kWh</strong>
            </div>
          ))}
        </div>
      </details>
    </>
  );
}
