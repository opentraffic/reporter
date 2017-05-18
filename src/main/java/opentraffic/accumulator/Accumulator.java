package opentraffic.accumulator;

import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.processor.TopologyBuilder;

public class Accumulator {
  public static void main(String[] args) throws Exception {   
    //some init
    Properties props = new Properties();
    props.put(StreamsConfig.APPLICATION_ID_CONFIG, "accumulator");
    props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(StreamsConfig.KEY_SERDE_CLASS_CONFIG, Serdes.String().getClass());
    props.put(StreamsConfig.VALUE_SERDE_CLASS_CONFIG, Serdes.String().getClass());
    //for now lets just start streaming from the beginning instead of coming in mid stream
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    //hook stuff together
    TopologyBuilder builder = new TopologyBuilder();
    builder.addSource("Source", "Raw");
    builder.addProcessor("Formatter", new KeyedFormattingProcessor(args), "Source");
    builder.addProcessor("Batcher", new BatchingProcessor(args), "Formatter");
    builder.addStateStore(BatchingProcessor.GetStore(), "Batcher");
    builder.addSink("Sink", "Segments", "Batcher");

    //run it
    KafkaStreams streams = new KafkaStreams(builder, props);
    streams.start();

    //kill it after 5 seconds (usually the stream application would be running forever)
    Thread.sleep(5000L);  
    streams.close();
  }
}