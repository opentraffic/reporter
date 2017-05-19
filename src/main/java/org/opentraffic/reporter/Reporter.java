package org.opentraffic.reporter;

import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.processor.TopologyBuilder;

public class Reporter {
  public static void main(String[] args) throws Exception {
    Properties props = new Properties();
    //for now lets just start streaming from the beginning instead of coming in mid stream
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    //some init
    props.put(StreamsConfig.APPLICATION_ID_CONFIG, "reporter");
    props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(StreamsConfig.KEY_SERDE_CLASS_CONFIG, Serdes.String().getClass());
    props.put(StreamsConfig.VALUE_SERDE_CLASS_CONFIG, Serdes.String().getClass());

    //hook stuff together
    Point.Serder pointSerder = new Point.Serder();
    TopologyBuilder builder = new TopologyBuilder();
    
    //takes raw input from tnc and reformat the tnc format data into
    //a key of string type and a value of Point type
    builder.addSource("Source", new StringDeserializer(), new StringDeserializer(), "Raw");
    builder.addProcessor("Formatter", new KeyedFormattingProcessor(args), "Source");
    builder.addSink("KeyedPointsSink", "Points", new StringSerializer(), pointSerder.serializer(), "Formatter");
    
    //take batches of points for a given key (uuid) and when some threshold is met
    //send that batch of points off to the reporter to be matched and update the
    //batch according to how much of the batch was used in matching
    builder.addSource("KeyedPointsSource", new StringDeserializer(), pointSerder.deserializer(), "Points");
    builder.addProcessor("Batcher", new BatchingProcessor(args), "KeyedPointsSource");
    builder.addStateStore(BatchingProcessor.GetStore(), "Batcher");
    builder.addSink("Sink", "Segments", "Batcher");
    
    //start consuming
    List<String> topics = new ArrayList<String>();
    topics.add("Segments");
    PrintConsumer consumer = new PrintConsumer(topics);
    consumer.setDaemon(true);
    consumer.start();
    
    //start the topology
    KafkaStreams streams = new KafkaStreams(builder, props);
    streams.start();
    
    //start producing
    FileProducer producer = new FileProducer("Raw", new String[]{"input"});
    producer.start();
    producer.join();

    pointSerder.close();
    streams.close();
  }
}