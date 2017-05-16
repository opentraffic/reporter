package opentraffic.accumulator;

import java.util.Iterator;

import org.apache.flink.api.common.restartstrategy.RestartStrategies;
import org.apache.flink.api.java.utils.ParameterTool;
import org.apache.flink.streaming.api.TimeCharacteristic;
import org.apache.flink.streaming.api.datastream.DataStreamSource;
import org.apache.flink.streaming.api.datastream.KeyedStream;
import org.apache.flink.streaming.api.datastream.SingleOutputStreamOperator;
import org.apache.flink.streaming.api.datastream.WindowedStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.AssignerWithPeriodicWatermarks;
import org.apache.flink.streaming.api.functions.windowing.WindowFunction;
import org.apache.flink.streaming.api.watermark.Watermark;
import org.apache.flink.streaming.api.windowing.assigners.EventTimeSessionWindows;
import org.apache.flink.streaming.api.windowing.evictors.Evictor;
import org.apache.flink.streaming.api.windowing.time.Time;
import org.apache.flink.streaming.api.windowing.triggers.Trigger;
import org.apache.flink.streaming.api.windowing.triggers.TriggerResult;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.streaming.connectors.kafka.FlinkKafkaConsumer010;
import org.apache.flink.streaming.runtime.operators.windowing.TimestampedValue;
import org.apache.flink.util.Collector;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class Accumulator {
  
  //TODO: get these magic constants from arguments
  private static final long REPORT_TIME_MIN = 60000;
  private static final long SESSION_GAP_MIN = 60000;
  private static final int REPORT_COUNT_MIN = 10;
  private static String url;
  
  public static void main(String[] args) throws Exception {
    //some argument parsing
    final ParameterTool params = ParameterTool.fromArgs(args);
    
    //we need args
    url = params.get("reporter");
    if(params.getNumberOfParameters() == 0 || url == null) {
      System.out.println("Usage: " + args[0] + " --file some_file --reporter http://some.reporter.url/report?");
      System.out.println("Usage: " + args[0] + " --topic some_topic --bootstrap.servers kafka_brokers --zookeeper.connect zk_quorum --group.id some_id --reporter http://some.reporter.url/report?");
      return;
    }
    
    //check file based input
    String file_path = params.get("file");
    if (file_path != null && file_path.isEmpty()) {
      System.out.println("Usage: " + args[0] +  " --file some_file --reporter http://some.reporter.url/report?");
      return;
    }
    
    //check kafka based input
    //NOTE: dont change how these args are parsed/named for kafka specific ones
    if (file_path == null && (params.get("topic") == null || params.get("bootstrap.servers") == null ||
        params.get("zookeeper.connect") == null || params.get("group.id") == null)) {
      System.out.println("Usage: " + args[0] + " --topic some_topic --bootstrap.servers kafka_brokers --zookeeper.connect zk_quorum --group.id some_id --reporter http://some.reporter.url/report?");
      return;
    }

    //execution environment
    StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
    //some options to configure
    env.getConfig().disableSysoutLogging();
    env.getConfig().setRestartStrategy(RestartStrategies.fixedDelayRestart(4, 10000));
    //create a checkpoint every 5 seconds
    env.enableCheckpointing(5000);
    //make parameters available in the web interface
    env.getConfig().setGlobalJobParameters(params);
    //using event time to measure progress
    env.setStreamTimeCharacteristic(TimeCharacteristic.EventTime);
    
    //get the data from some configured location, use a custom deserialization schema to get GPSMessage objects in the window
    DataStreamSource<GPSMessage> unassigned_stream = file_path != null ? 
      env.readFile(new GPSMessageSchema(), params.get("file")) : 
      env.addSource(new FlinkKafkaConsumer010<GPSMessage>(params.get("topic"), new GPSMessageSchema(), params.getProperties()));

    //we need to tell flink about timestamps and watermarks to use eventtime driven streaming
    SingleOutputStreamOperator<GPSMessage> assigned_stream = unassigned_stream.assignTimestampsAndWatermarks(new GPSPunctuatedAssigner());
    
    //use a lambda to supply the uuid field of the GPSMessage as the key to group messages for parallel processing
    //this way a given window contains only messages with the same uuid, so we can do work on different uuids async
    KeyedStream<GPSMessage, String> keyed = assigned_stream.keyBy((event) -> event.uuid);
    
    //get a session based window so that inactivity of a given uuid will close the window (session)
    WindowedStream<GPSMessage, String, TimeWindow> windowed = keyed.window(EventTimeSessionWindows.withGap(Time.milliseconds(SESSION_GAP_MIN)));
    
    //trigger for when to do some work on a window, we'll want to evict some of the messages up to the ones we'll need to use for later
    windowed.trigger(new GPSTrigger());
    
    //an evictor for when to remove some of the accumulated gps messages
    windowed.evictor(new GPSEvictor());
    
    //a window function that will do the actual work on a given window when the trigger is hit and when the window closed
    windowed.apply(new GPSWindowFunction()).print();

    //run it
    env.execute("Aggregator");
  }
  
  //a timestamp watermark assigner for gps messages
  public static class GPSPunctuatedAssigner implements AssignerWithPeriodicWatermarks<GPSMessage> {
    private static final long serialVersionUID = 1L;
    private final long slack = 5000l;
    private long max_timestamp;
    @Override
    public long extractTimestamp(GPSMessage element, long previousElementTimestamp) {
      long timestamp = element.epoch;
      max_timestamp = Math.max(timestamp, max_timestamp);
      return timestamp;
    }
    @Override
    public Watermark getCurrentWatermark() {
      //the watermark allows for some slack, not sure if this is needed
      return new Watermark(max_timestamp - slack);
    }
  }
  
  //a custom trigger to work with our session based time window
  private static class GPSTrigger extends Trigger<GPSMessage, TimeWindow> {
    private static final long serialVersionUID = 1L;
    @Override
    public TriggerResult onElement(GPSMessage element, long timestamp, TimeWindow window, TriggerContext ctx) {
      //only fire if we its been enough elapsed event time (TODO: and we have a reasonable number of points)
      return window.getEnd() - window.getStart() >= REPORT_TIME_MIN ? TriggerResult.FIRE : TriggerResult.CONTINUE;
    }
    @Override
    public TriggerResult onProcessingTime(long time, TimeWindow window, TriggerContext ctx) {
      return TriggerResult.CONTINUE;    
    }
    @Override
    public TriggerResult onEventTime(long time, TimeWindow window, TriggerContext ctx) {
      return TriggerResult.CONTINUE;
    }
    @Override
    public boolean canMerge() {
      return true;
    }
    @Override
    public void onMerge(TimeWindow window, OnMergeContext ctx) {
      //TODO: since onElement will be called after this maybe we dont need to do anything here?
    }
    @Override
    public void clear(TimeWindow window, TriggerContext ctx) {
      //TODO: this happens on a purge so we probably dont need to do anything with it?
    }
  }
  
  //a custom evictor to get ride of data from the window that we've used
  private static class GPSEvictor implements Evictor<GPSMessage, TimeWindow> {
    private static final long serialVersionUID = 1L;
    @Override
    public void evictBefore(Iterable<TimestampedValue<GPSMessage>> elements, int size, TimeWindow window, EvictorContext ctx) {
      //we dont need to evict stuff before we've executed the window function
    }
    @Override
    public void evictAfter(Iterable<TimestampedValue<GPSMessage>> elements, int size, TimeWindow window, EvictorContext ctx) {
      //after we've exectued the window function we want to purge some of the elements that we wont need next time it executes
      for (Iterator<TimestampedValue<GPSMessage>> iterator = elements.iterator(); iterator.hasNext();)
        if (iterator.next().getStreamRecord().getValue().trace == null)
          iterator.remove();
    }   
  }
  
  //a custom response that we expect to get back from the reporter
  private static class ReporterResponse {
    @JsonCreator
    public ReporterResponse(@JsonProperty("shape_used") int shape_used, @JsonProperty("error") String error) {
      this.shape_used = shape_used;
      this.error = error;
    }
    @JsonCreator
    public ReporterResponse(@JsonProperty("shape_used") int shape_used) {
      this.shape_used = shape_used;
      this.error = null;
    }
    @JsonCreator
    public ReporterResponse(@JsonProperty("error") String error) {
      this.shape_used = -1;
      this.error = error;
    }
    private int shape_used;
    private String error;
  }  
  
  //a custom window function to do work on the window each time we get triggered
  private static class GPSWindowFunction implements WindowFunction<GPSMessage, String, String, TimeWindow> {
    private static final long serialVersionUID = 1L;
    public void apply(String key, TimeWindow window, Iterable<GPSMessage> input, Collector<String> output) {
      //make the request
      long count = 0;
      StringBuilder sb = new StringBuilder();
      sb.ensureCapacity(REPORT_COUNT_MIN * GPSMessage.appxWireSize);
      sb.append("{\"uuid\":\""); sb.append(key); sb.append("\",\"trace\":[");
      for (GPSMessage m : input) {
        count++;
        sb.append(m.trace);
        sb.append(',');
      }
      //if its not enough to warrant use then skip it for now unless the purge processing time trigger is forcing it
      if(count < REPORT_COUNT_MIN)
        return;
      //finish up the json
      sb.replace(sb.length() - 1, sb.length() - 1, "]}");
      String post_body = sb.toString();
      //synchronously make the request to the see how much of it was used
      try {
        ReporterResponse response = HttpClient.POST(url, post_body);
        if(response.error != null && response.shape_used != -1)
          count = response.shape_used;
      }
      catch (Exception e) {  }
      //let downstream know how much of the window we used
      output.collect(Long.toString(count));
      //mark the portion of the window that was used so the evictor can delete it
      for (GPSMessage m : input) {
        //we are done marking
        if(count == 0)
          break;
        count--;
        //mark with null uuid for eviction
        m.trace = null;
      }
    }
  }
}